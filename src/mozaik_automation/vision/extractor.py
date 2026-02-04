"""
Drawing extraction using vision models.

This module handles the extraction of room geometry and cabinet specifications
from various input formats (PDF, images, sketches) using multimodal vision models.
"""

import base64
import json
from pathlib import Path
from typing import Any, Literal, Optional

from PIL import Image

from mozaik_automation.models import CabinetSpec


class DrawingExtractor:
    """
    Extracts cabinet specifications from drawings using vision models.

    Supports multiple backends:
    - OpenAI GPT-4V
    - Anthropic Claude
    - Ollama (local vision models via API)
    - Local models (LLaVA, etc.)
    """

    def __init__(
        self,
        backend: Literal["openai", "anthropic", "ollama", "local"] = "anthropic",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        ollama_host: Optional[str] = None,
    ):
        self.backend = backend
        self.model = model or self._default_model()
        self.api_key = api_key
        self.ollama_host = ollama_host or "http://14coresbeast:11434"
        self._client = None

    def _default_model(self) -> str:
        """Get default model for backend."""
        defaults = {
            "openai": "gpt-4o",
            "anthropic": "claude-sonnet-4-20250514",
            "ollama": "minicpm-v:latest",
            "local": "llava-v1.6-mistral-7b",
        }
        return defaults.get(self.backend, "gpt-4o")

    def _get_client(self):
        """Initialize API client lazily."""
        if self._client is not None:
            return self._client

        if self.backend == "openai":
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key)
        elif self.backend == "anthropic":
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        else:
            # Local model setup would go here
            pass

        return self._client

    def _load_image(self, image_path: Path) -> tuple[str, str]:
        """Load and encode image as base64."""
        with open(image_path, "rb") as f:
            data = f.read()

        # Determine media type
        suffix = image_path.suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_types.get(suffix, "image/png")

        return base64.standard_b64encode(data).decode("utf-8"), media_type

    def _pdf_to_images(self, pdf_path: Path) -> list[Image.Image]:
        """Convert PDF pages to images."""
        try:
            from pdf2image import convert_from_path

            return convert_from_path(pdf_path, dpi=150)
        except ImportError:
            raise ImportError("pdf2image is required for PDF processing")

    def _build_extraction_prompt(self) -> str:
        """Build the prompt for cabinet extraction."""
        return """Analyze this architectural drawing and extract cabinet design specifications.

You are an expert cabinet designer. Extract all visible information about:

1. **Room Geometry**:
   - Wall positions and lengths (in inches or mm as shown)
   - Ceiling height
   - Door and window openings with positions

2. **Cabinet Layout**:
   - Each cabinet's type (base, wall, tall, corner, island)
   - Position along wall (offset from start)
   - Dimensions (width, height, depth)
   - Configuration (doors, drawers, hinges)

3. **Appliances**:
   - Type (range, sink, refrigerator, etc.)
   - Position and dimensions

4. **Finishes** (if visible/noted):
   - Door style
   - Material/color
   - Hardware

Return a JSON object matching this schema:
{
  "metadata": {"job_name": "...", "source_type": "floor_plan|elevation|sketch"},
  "room": {
    "units": "in",
    "ceiling_height": 96,
    "walls": [{"id": "W1", "start": [0,0], "end": [156,0]}],
    "openings": [{"type": "window", "wall_id": "W1", "offset": 48, "width": 36, "height": 48}]
  },
  "cabinets": [
    {
      "id": "B1",
      "cabinet_type": "base",
      "position": {"wall_id": "W1", "offset": 0},
      "dimensions": {"width": 24, "height": 34.5, "depth": 24}
    }
  ],
  "appliances": []
}

Be precise with measurements. If dimensions aren't clear, estimate based on standard cabinet sizes.
Only include what you can see or reasonably infer from the drawing.
"""

    def extract(
        self,
        source: str | Path,
        source_type: Literal["auto", "floor_plan", "elevation", "sketch"] = "auto",
    ) -> dict[str, Any]:
        """
        Extract cabinet specifications from a drawing.

        Args:
            source: Path to image or PDF file
            source_type: Type of drawing (auto-detected if not specified)

        Returns:
            Dictionary matching cabinet_spec schema
        """
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        # Handle PDF
        if source.suffix.lower() == ".pdf":
            images = self._pdf_to_images(source)
            # Process first page for now (could combine multiple)
            import io

            buffer = io.BytesIO()
            images[0].save(buffer, format="PNG")
            buffer.seek(0)
            image_data = base64.standard_b64encode(buffer.read()).decode("utf-8")
            media_type = "image/png"
        else:
            image_data, media_type = self._load_image(source)

        # Call vision model
        prompt = self._build_extraction_prompt()

        if self.backend == "anthropic":
            result = self._extract_anthropic(image_data, media_type, prompt)
        elif self.backend == "openai":
            result = self._extract_openai(image_data, media_type, prompt)
        elif self.backend == "ollama":
            result = self._extract_ollama(image_data, media_type, prompt)
        else:
            result = self._extract_local(image_data, prompt)

        # Add source metadata
        result.setdefault("metadata", {})
        result["metadata"]["source_file"] = str(source)
        result["metadata"]["source_type"] = source_type if source_type != "auto" else "floor_plan"

        return result

    def _extract_anthropic(
        self, image_data: str, media_type: str, prompt: str
    ) -> dict[str, Any]:
        """Extract using Anthropic Claude."""
        client = self._get_client()

        message = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        # Parse JSON from response
        response_text = message.content[0].text
        return self._parse_json_response(response_text)

    def _extract_openai(
        self, image_data: str, media_type: str, prompt: str
    ) -> dict[str, Any]:
        """Extract using OpenAI GPT-4V."""
        client = self._get_client()

        response = client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        response_text = response.choices[0].message.content
        return self._parse_json_response(response_text)

    def _extract_ollama(
        self, image_data: str, media_type: str, prompt: str
    ) -> dict[str, Any]:
        """Extract using Ollama vision model via REST API."""
        import httpx

        url = f"{self.ollama_host}/api/chat"

        # Ollama expects images as base64 in the images array
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data],
                }
            ],
            "stream": False,
        }

        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=300.0,  # 5 minutes for CPU inference
            )
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Could not connect to Ollama at {self.ollama_host}. "
                f"Ensure Ollama is running: {e}"
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama API error: {e.response.status_code} - {e.response.text}")

        result = response.json()
        response_text = result.get("message", {}).get("content", "")

        return self._parse_json_response(response_text)

    def _extract_local(self, image_data: str, prompt: str) -> dict[str, Any]:
        """Extract using local model (e.g., LLaVA)."""
        # This would integrate with llama-cpp-python or similar
        raise NotImplementedError("Local model extraction not yet implemented")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from model response, handling various formats."""
        import re
        import logging

        logger = logging.getLogger(__name__)

        # Log raw response for debugging
        logger.debug(f"Raw vision response ({len(text)} chars): {text[:500]}...")

        # Strip markdown code blocks if present
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        # Try to find JSON object in the text
        # Look for outermost { ... }
        brace_start = text.find("{")
        if brace_start >= 0:
            # Find matching closing brace
            depth = 0
            for i, c in enumerate(text[brace_start:], brace_start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[brace_start:i+1]
                        break

        # Try to parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}. Trying cleanup...")

            # Common fixes for LLM output
            # Remove trailing commas before } or ]
            text = re.sub(r',\s*}', '}', text)
            text = re.sub(r',\s*]', ']', text)

            # Try again
            return json.loads(text)

    def extract_to_spec(
        self,
        source: str | Path,
        source_type: Literal["auto", "floor_plan", "elevation", "sketch"] = "auto",
    ) -> CabinetSpec:
        """
        Extract and validate as CabinetSpec model.

        Args:
            source: Path to image or PDF file
            source_type: Type of drawing

        Returns:
            Validated CabinetSpec model
        """
        raw = self.extract(source, source_type)
        return CabinetSpec.model_validate(raw)
