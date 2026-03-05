"""
Tests for vision extraction.

TDD: These tests define the expected behavior of vision-based extraction.
All API calls are mocked to avoid external dependencies.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mozaik_automation.vision.extractor import DrawingExtractor


class TestDrawingExtractor:
    """Tests for DrawingExtractor class."""

    def test_create_extractor_default(self):
        """Should create extractor with defaults."""
        extractor = DrawingExtractor()
        assert extractor.backend == "anthropic"
        assert extractor.model == "claude-sonnet-4-20250514"

    def test_create_extractor_openai(self):
        """Should create extractor with OpenAI backend."""
        extractor = DrawingExtractor(backend="openai")
        assert extractor.backend == "openai"
        assert extractor.model == "gpt-4o"

    def test_create_extractor_custom_model(self):
        """Should accept custom model."""
        extractor = DrawingExtractor(
            backend="anthropic", model="claude-opus-4-20250514"
        )
        assert extractor.model == "claude-opus-4-20250514"


class TestExtractionPrompt:
    """Tests for extraction prompt generation."""

    def test_prompt_includes_room_geometry(self):
        """Prompt should request room geometry extraction."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()

        assert "room" in prompt.lower()
        assert "wall" in prompt.lower()
        assert "ceiling" in prompt.lower()

    def test_prompt_includes_cabinet_layout(self):
        """Prompt should request cabinet layout extraction."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()

        assert "cabinet" in prompt.lower()
        assert "base" in prompt.lower()
        assert "wall" in prompt.lower()

    def test_prompt_requests_json(self):
        """Prompt should request JSON output."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()

        assert "JSON" in prompt


class TestExtractionPromptPollerFormat:
    """T005: Tests that extraction prompt contains all poller-compatible fields."""

    def test_prompt_contains_room_shape(self):
        """Prompt must request room.shape field."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "shape" in prompt.lower()
        assert "U-shape" in prompt or "single-wall" in prompt

    def test_prompt_contains_wall_names(self):
        """Prompt must specify wall naming convention."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        for name in ["left", "back", "right"]:
            assert name in prompt.lower()

    def test_prompt_contains_cabinet_wall_reference(self):
        """Prompt must show cabinets reference a wall by name."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert '"wall"' in prompt

    def test_prompt_contains_position_along_wall(self):
        """Prompt must include position_along_wall field and formula."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "position_along_wall" in prompt
        assert "cumulative_width" in prompt or "cumulative" in prompt.lower()

    def test_prompt_contains_parsed_counts(self):
        """Prompt must include parsed counts (base/wall/tall)."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert '"parsed"' in prompt
        assert '"base"' in prompt
        assert '"wall"' in prompt
        assert '"tall"' in prompt

    def test_prompt_contains_appliances_section(self):
        """Prompt must include appliances array in schema."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert '"appliances"' in prompt
        assert "sink" in prompt.lower()
        assert "range" in prompt.lower()
        assert "refrigerator" in prompt.lower()


class TestExtractionClassificationRules:
    """T006: Tests that extraction prompt enforces Mozaik classification rules."""

    def test_fridge_is_appliance_not_cabinet(self):
        """Fridges must be classified as appliance, never tall cabinet."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "refrigerator" in prompt.lower()
        assert "NEVER" in prompt  # "NEVER cabinet: tall" rule
        # Check the rule is explicit
        assert "appliance" in prompt.lower()

    def test_skip_dishwashers(self):
        """Dishwashers must be skipped entirely."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "dishwasher" in prompt.lower()
        assert "SKIP" in prompt

    def test_skip_microwaves(self):
        """Microwaves must be skipped entirely."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "microwave" in prompt.lower()
        assert "SKIP" in prompt

    def test_builtin_oven_is_tall_cabinet(self):
        """Built-in wall oven must be classified as tall cabinet with note."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "oven" in prompt.lower()
        assert "tall" in prompt.lower()
        assert "note" in prompt.lower() or "oven cabinet" in prompt.lower()

    def test_range_is_appliance(self):
        """Freestanding/slide-in range must be classified as appliance."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "range" in prompt.lower()
        assert "appliance" in prompt.lower()

    def test_hood_is_appliance(self):
        """Range hood must be classified as appliance."""
        extractor = DrawingExtractor()
        prompt = extractor._build_extraction_prompt()
        assert "hood" in prompt.lower()


class TestJsonParsing:
    """Tests for JSON response parsing."""

    def test_parse_clean_json(self):
        """Should parse clean JSON."""
        extractor = DrawingExtractor()
        json_text = '{"metadata": {"job_name": "Test"}, "room": {}, "cabinets": []}'
        result = extractor._parse_json_response(json_text)

        assert result["metadata"]["job_name"] == "Test"

    def test_parse_json_with_markdown_block(self):
        """Should parse JSON wrapped in markdown code block."""
        extractor = DrawingExtractor()
        json_text = '''Here is the extracted data:

```json
{"metadata": {"job_name": "Test"}, "room": {}, "cabinets": []}
```

Let me know if you need more details.'''

        result = extractor._parse_json_response(json_text)
        assert result["metadata"]["job_name"] == "Test"

    def test_parse_json_with_plain_code_block(self):
        """Should parse JSON wrapped in plain code block."""
        extractor = DrawingExtractor()
        json_text = '''```
{"metadata": {"job_name": "Test"}, "room": {}, "cabinets": []}
```'''

        result = extractor._parse_json_response(json_text)
        assert result["metadata"]["job_name"] == "Test"


class TestImageLoading:
    """Tests for image loading functionality."""

    def test_load_png_image(self, tmp_path):
        """Should load and encode PNG image."""
        # Create a simple PNG file (1x1 red pixel)
        test_image = tmp_path / "test.png"
        # Minimal PNG header + data
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A  # PNG signature
        ])
        test_image.write_bytes(png_data)

        extractor = DrawingExtractor()
        data, media_type = extractor._load_image(test_image)

        assert isinstance(data, str)  # Base64 encoded
        assert media_type == "image/png"

    def test_load_jpg_image(self, tmp_path):
        """Should load and encode JPG image."""
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"fake jpg data")

        extractor = DrawingExtractor()
        data, media_type = extractor._load_image(test_image)

        assert media_type == "image/jpeg"

    def test_load_jpeg_image(self, tmp_path):
        """Should handle .jpeg extension."""
        test_image = tmp_path / "test.jpeg"
        test_image.write_bytes(b"fake jpg data")

        extractor = DrawingExtractor()
        data, media_type = extractor._load_image(test_image)

        assert media_type == "image/jpeg"


class TestExtraction:
    """Tests for main extraction method."""

    def test_extract_file_not_found(self):
        """Should raise error for non-existent file."""
        extractor = DrawingExtractor()

        with pytest.raises(FileNotFoundError):
            extractor.extract("/nonexistent/file.png")

    def test_extract_adds_source_metadata(self, tmp_path):
        """Should add source file to metadata."""
        test_image = tmp_path / "floor_plan.png"
        test_image.write_bytes(b"fake image")

        extractor = DrawingExtractor()

        # Mock the API call
        mock_response = {
            "metadata": {"job_name": "Test Job"},
            "room": {
                "units": "in",
                "ceiling_height": 96,
                "walls": [],
            },
            "cabinets": [],
        }

        with patch.object(extractor, "_extract_anthropic", return_value=mock_response):
            result = extractor.extract(test_image, source_type="floor_plan")

        assert result["metadata"]["source_file"] == str(test_image)
        assert result["metadata"]["source_type"] == "floor_plan"


class TestAnthropicExtraction:
    """Tests for Anthropic API extraction."""

    def test_anthropic_extraction_structure(self, tmp_path):
        """Should call Anthropic API with correct structure."""
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"fake image")

        extractor = DrawingExtractor(backend="anthropic")

        # Mock the client
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(text='{"metadata": {"job_name": "Test"}, "room": {"units": "in", "ceiling_height": 96, "walls": []}, "cabinets": []}')
        ]
        mock_client.messages.create.return_value = mock_message

        with patch.object(extractor, "_get_client", return_value=mock_client):
            extractor.extract(test_image)

        # Verify API was called
        mock_client.messages.create.assert_called_once()
        call_args = mock_client.messages.create.call_args

        # Check message structure
        assert call_args.kwargs["model"] == "claude-sonnet-4-20250514"
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

        # Should have image and text content
        content = messages[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "image"
        assert content[1]["type"] == "text"


class TestOpenAIExtraction:
    """Tests for OpenAI API extraction."""

    def test_openai_extraction_structure(self, tmp_path):
        """Should call OpenAI API with correct structure."""
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"fake image")

        extractor = DrawingExtractor(backend="openai")

        # Mock the client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"metadata": {"job_name": "Test"}, "room": {"units": "in", "ceiling_height": 96, "walls": []}, "cabinets": []}'
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.object(extractor, "_get_client", return_value=mock_client):
            extractor.extract(test_image)

        # Verify API was called
        mock_client.chat.completions.create.assert_called_once()


class TestExtractToSpec:
    """Tests for extraction with validation."""

    def test_extract_to_spec_returns_model(self, tmp_path):
        """Should return validated CabinetSpec model."""
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"fake image")

        extractor = DrawingExtractor()

        mock_response = {
            "metadata": {"job_name": "Test Job"},
            "room": {
                "units": "in",
                "ceiling_height": 96,
                "walls": [
                    {"id": "W1", "start": [0, 0], "end": [100, 0]}
                ],
                "openings": [],
            },
            "cabinets": [
                {
                    "id": "B1",
                    "cabinet_type": "base",
                    "position": {"wall_id": "W1", "offset": 0},
                    "dimensions": {"width": 24},
                }
            ],
        }

        with patch.object(extractor, "_extract_anthropic", return_value=mock_response):
            result = extractor.extract_to_spec(test_image)

        from mozaik_automation.models import CabinetSpec
        assert isinstance(result, CabinetSpec)
        assert result.metadata.job_name == "Test Job"
        assert len(result.cabinets) == 1
