# Vision Extraction Standards

Standards for extracting cabinet specifications from floor plans using vision models.

> **Base Standards:** See [project-manager/docs/standards/agent-context.md](https://github.com/mv2a/project-manager/blob/main/docs/standards/agent-context.md)

---

## Vision Backends

| Backend | Model | Use Case | Performance |
|---------|-------|----------|-------------|
| `openai` | GPT-4V | Production extraction | ~3-5s, high accuracy |
| `anthropic` | Claude | Alternative/validation | ~3-5s, high accuracy |
| `local` | Ollama minicpm-v | Offline development | ~10s, lower accuracy |

### Backend Selection

```python
from mozaik_automation.vision.extractor import VisionExtractor

# Production
extractor = VisionExtractor(backend="openai")

# Development (no API costs)
extractor = VisionExtractor(backend="local")

# Validation (cross-check results)
extractor = VisionExtractor(backend="anthropic")
```

---

## Input Image Requirements

### Supported Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| PNG | `.png` | Preferred for floor plans |
| JPEG | `.jpg`, `.jpeg` | Acceptable |
| PDF | `.pdf` | First page extracted |
| TIFF | `.tif`, `.tiff` | High-res scans |

### Image Quality Guidelines

| Criterion | Minimum | Recommended |
|-----------|---------|-------------|
| Resolution | 1000x1000 | 2000x2000+ |
| DPI | 150 | 300+ |
| File size | 100KB | 500KB-5MB |
| Color depth | Grayscale | RGB |

### Preprocessing

```python
from PIL import Image, ImageEnhance

def preprocess_floor_plan(image_path: str) -> Image:
    """Prepare image for vision extraction."""
    img = Image.open(image_path)

    # Convert to RGB if needed
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Enhance contrast for line detection
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    # Resize if too large (keep aspect ratio)
    max_dim = 4096
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    return img
```

---

## Output Schema

### CabinetSpec Structure

```python
from pydantic import BaseModel
from typing import List, Optional

class Room(BaseModel):
    name: str
    walls: List[Wall]
    openings: List[Opening]
    ceiling_height: float  # inches

class Cabinet(BaseModel):
    type: str  # "base", "wall", "tall"
    position: Position
    dimensions: Dimensions
    configuration: str  # "sink_base", "lazy_susan", etc.

class CabinetSpec(BaseModel):
    metadata: Metadata
    room: Room
    cabinets: List[Cabinet]
    appliances: List[Appliance]
    finishes: List[FinishPackage]
```

### JSON Output Format

```json
{
  "metadata": {
    "job_name": "Smith Kitchen Renovation",
    "client": "John Smith",
    "source": "floor_plan_001.png"
  },
  "room": {
    "name": "Kitchen",
    "ceiling_height": 96,
    "walls": [
      {"start": {"x": 0, "y": 0}, "end": {"x": 120, "y": 0}, "height": 96}
    ],
    "openings": [
      {"type": "door", "wall_index": 0, "position": 60, "width": 36, "height": 80}
    ]
  },
  "cabinets": [
    {
      "type": "base",
      "position": {"x": 0, "y": 0, "wall_index": 0},
      "dimensions": {"width": 36, "height": 34.5, "depth": 24},
      "configuration": "standard_3_drawer"
    }
  ],
  "appliances": [
    {
      "type": "refrigerator",
      "brand": "Samsung",
      "model": "RF28",
      "position": {"x": 100, "y": 0}
    }
  ],
  "finishes": []
}
```

---

## Prompt Engineering

### System Prompt Template

```python
EXTRACTION_SYSTEM_PROMPT = """
You are a cabinet design expert analyzing architectural floor plans.
Extract cabinet specifications following this exact JSON schema:

{schema}

Guidelines:
1. All dimensions in INCHES
2. Position coordinates relative to room origin (lower-left corner)
3. Wall indices start at 0, clockwise from bottom wall
4. Include ALL visible cabinets, not just labeled ones
5. Infer cabinet types from standard dimensions when not labeled
6. Mark uncertain values with "confidence": "low"
"""
```

### User Prompt Template

```python
EXTRACTION_USER_PROMPT = """
Analyze this floor plan image and extract:
1. Room dimensions and wall layout
2. All cabinets (base, wall, tall) with positions and dimensions
3. Appliances with brand/model if visible
4. Door and window openings

Return ONLY valid JSON matching the schema. No explanations.
"""
```

### Few-Shot Examples

For improved accuracy, include 2-3 examples in the prompt:

```python
FEW_SHOT_EXAMPLE = """
Example input: [Image of L-shaped kitchen with peninsula]
Example output:
{
  "room": {"name": "Kitchen", "ceiling_height": 96, ...},
  "cabinets": [
    {"type": "base", "configuration": "sink_base", ...},
    {"type": "base", "configuration": "peninsula_end", ...},
    {"type": "wall", "configuration": "standard", ...}
  ]
}
"""
```

---

## Validation

### Schema Validation

```python
from jsonschema import validate

def validate_extraction(result: dict) -> List[str]:
    """Validate extracted spec against schema."""
    errors = []

    # Schema validation
    try:
        validate(result, CABINET_SPEC_SCHEMA)
    except ValidationError as e:
        errors.append(f"Schema error: {e.message}")

    # Business rules
    errors.extend(validate_business_rules(result))

    return errors

def validate_business_rules(result: dict) -> List[str]:
    """Validate domain-specific rules."""
    errors = []

    # Cabinet dimensions must be reasonable
    for cab in result.get("cabinets", []):
        width = cab["dimensions"]["width"]
        if width < 9 or width > 48:
            errors.append(f"Cabinet width {width} outside valid range (9-48)")

    # Base cabinets must have standard height
    for cab in result.get("cabinets", []):
        if cab["type"] == "base":
            height = cab["dimensions"]["height"]
            if height not in [34.5, 35, 36]:
                errors.append(f"Base cabinet height {height} non-standard")

    return errors
```

### Confidence Scoring

```python
def compute_confidence(result: dict) -> float:
    """Compute overall extraction confidence."""
    scores = []

    # Check completeness
    if result.get("room", {}).get("walls"):
        scores.append(1.0)
    else:
        scores.append(0.0)

    # Check cabinet count vs room size
    room_area = compute_room_area(result.get("room", {}))
    cabinet_count = len(result.get("cabinets", []))
    expected_cabinets = room_area / 50  # ~1 cabinet per 50 sq in
    if abs(cabinet_count - expected_cabinets) < expected_cabinets * 0.5:
        scores.append(1.0)
    else:
        scores.append(0.5)

    return sum(scores) / len(scores)
```

---

## Evaluation Metrics

### Accuracy Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| Room accuracy | Correct wall count and dimensions | >90% |
| Cabinet count | Correct number of cabinets | >85% |
| Dimension accuracy | Within 2" of ground truth | >80% |
| Position accuracy | Within 6" of ground truth | >75% |
| Configuration accuracy | Correct cabinet type | >85% |

### Evaluation Script

```python
from mozaik_automation.training.evaluation import ExtractionEvaluator

evaluator = ExtractionEvaluator()

# Load golden test set
golden = load_jsonl("data/eval/golden.jsonl")

# Evaluate extraction
for sample in golden:
    image_path = sample["image"]
    expected = sample["spec"]

    actual = extractor.extract(image_path)

    metrics = evaluator.compare(expected, actual)
    print(f"Precision: {metrics.precision:.2%}")
    print(f"Recall: {metrics.recall:.2%}")
    print(f"Dimension RMSE: {metrics.dimension_rmse:.1f} inches")
```

---

## Error Handling

### Common Extraction Failures

| Error | Cause | Mitigation |
|-------|-------|------------|
| Empty cabinets array | Low quality image | Enhance contrast, increase resolution |
| Missing walls | Complex layout | Use multi-pass extraction |
| Wrong dimensions | Scale not detected | Include scale reference in prompt |
| Duplicate cabinets | Overlapping annotations | Post-process deduplication |

### Retry Logic

```python
async def extract_with_retry(image_path: str, max_retries: int = 3):
    """Extract with exponential backoff."""
    for attempt in range(max_retries):
        try:
            result = await extractor.extract(image_path)
            if validate_extraction(result):
                return result
        except RateLimitError:
            await asyncio.sleep(2 ** attempt)
        except InvalidResponseError:
            # Try different prompt variation
            continue

    raise ExtractionError("Max retries exceeded")
```

---

## Cost Optimization

### Token Usage

| Image Size | Input Tokens | Typical Output | Cost (GPT-4V) |
|------------|--------------|----------------|---------------|
| 1000x1000 | ~1,000 | ~500 | ~$0.02 |
| 2000x2000 | ~2,500 | ~800 | ~$0.05 |
| 4000x4000 | ~5,000 | ~1,200 | ~$0.10 |

### Optimization Strategies

1. **Resize images** to max 2000x2000 before extraction
2. **Cache results** for identical images
3. **Batch similar layouts** for few-shot learning
4. **Use local models** for development/testing

---

*Last Updated: 2026-01-28*
