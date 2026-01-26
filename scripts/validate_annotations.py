#!/usr/bin/env python3
"""
Validate cabinet specification annotations against the schema.

This script validates annotation JSON files to ensure they conform to
the cabinet specification schema before training data preparation.

Usage:
    python validate_annotations.py --input data/raw/kitchens
    python validate_annotations.py --input data/raw/kitchens --verbose
    python validate_annotations.py --file data/samples/example_annotation.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()

# Schema path
SCHEMA_PATH = Path(__file__).parent.parent / "data" / "schemas" / "cabinet_spec.json"


def load_schema() -> dict[str, Any]:
    """Load the cabinet specification schema."""
    if SCHEMA_PATH.exists():
        return json.loads(SCHEMA_PATH.read_text())
    return {}


def validate_required_fields(
    data: dict[str, Any],
    required: list[str],
    path: str = "",
) -> list[str]:
    """Check for required fields, return list of errors."""
    errors = []
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {path}{field}")
    return errors


def validate_enum(
    value: Any,
    allowed: list[str],
    field_name: str,
) -> list[str]:
    """Validate value against allowed enum values."""
    if value not in allowed:
        return [f"Invalid value '{value}' for {field_name}. Allowed: {allowed}"]
    return []


def validate_array_items(
    items: list[Any],
    min_items: int,
    max_items: int,
    field_name: str,
) -> list[str]:
    """Validate array length constraints."""
    errors = []
    if len(items) < min_items:
        errors.append(f"{field_name} must have at least {min_items} items")
    if max_items and len(items) > max_items:
        errors.append(f"{field_name} must have at most {max_items} items")
    return errors


def validate_number_range(
    value: float,
    minimum: float | None,
    maximum: float | None,
    field_name: str,
) -> list[str]:
    """Validate number within range."""
    errors = []
    if minimum is not None and value < minimum:
        errors.append(f"{field_name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        errors.append(f"{field_name} must be <= {maximum}, got {value}")
    return errors


def validate_metadata(metadata: dict[str, Any]) -> list[str]:
    """Validate metadata section."""
    errors = []

    # Check job_name exists
    if "job_name" not in metadata:
        errors.append("metadata.job_name is required")

    # Check source_type enum
    if "source_type" in metadata:
        allowed = ["floor_plan", "elevation", "sketch", "photo", "cad"]
        errors.extend(validate_enum(
            metadata["source_type"],
            allowed,
            "metadata.source_type",
        ))

    # Check confidence_score range
    if "confidence_score" in metadata:
        errors.extend(validate_number_range(
            metadata["confidence_score"],
            0.0,
            1.0,
            "metadata.confidence_score",
        ))

    return errors


def validate_room(room: dict[str, Any]) -> list[str]:
    """Validate room section."""
    errors = []

    # Required fields
    errors.extend(validate_required_fields(
        room,
        ["units", "walls", "ceiling_height"],
        "room.",
    ))

    # Units enum
    if "units" in room:
        errors.extend(validate_enum(
            room["units"],
            ["in", "mm", "cm"],
            "room.units",
        ))

    # Ceiling height must be positive
    if "ceiling_height" in room:
        if room["ceiling_height"] <= 0:
            errors.append("room.ceiling_height must be positive")

    # Validate walls
    if "walls" in room:
        for i, wall in enumerate(room["walls"]):
            prefix = f"room.walls[{i}]."
            errors.extend(validate_required_fields(
                wall,
                ["id", "start", "end"],
                prefix,
            ))

            # Validate coordinate arrays
            if "start" in wall:
                errors.extend(validate_array_items(
                    wall["start"],
                    2, 2,
                    f"{prefix}start",
                ))
            if "end" in wall:
                errors.extend(validate_array_items(
                    wall["end"],
                    2, 2,
                    f"{prefix}end",
                ))

    # Validate openings
    if "openings" in room:
        for i, opening in enumerate(room.get("openings", [])):
            prefix = f"room.openings[{i}]."
            errors.extend(validate_required_fields(
                opening,
                ["type", "wall_id", "offset", "width", "height"],
                prefix,
            ))

            if "type" in opening:
                errors.extend(validate_enum(
                    opening["type"],
                    ["door", "window", "pass_through", "archway"],
                    f"{prefix}type",
                ))

    return errors


def validate_cabinets(cabinets: list[dict[str, Any]]) -> list[str]:
    """Validate cabinets section."""
    errors = []

    cabinet_types = [
        "base", "base_sink", "base_corner", "base_blind_corner",
        "wall", "wall_corner", "wall_blind_corner",
        "tall", "tall_pantry", "tall_oven",
        "island", "peninsula",
        "drawer_base", "appliance_garage",
        "open_shelf", "wine_rack",
    ]

    hinge_sides = ["left", "right", "both", "none"]
    overlay_types = ["full", "partial", "inset"]

    for i, cabinet in enumerate(cabinets):
        prefix = f"cabinets[{i}]."

        # Required fields
        errors.extend(validate_required_fields(
            cabinet,
            ["id", "cabinet_type", "position", "dimensions"],
            prefix,
        ))

        # Cabinet type enum
        if "cabinet_type" in cabinet:
            errors.extend(validate_enum(
                cabinet["cabinet_type"],
                cabinet_types,
                f"{prefix}cabinet_type",
            ))

        # Position validation
        if "position" in cabinet:
            pos = cabinet["position"]
            errors.extend(validate_required_fields(
                pos,
                ["wall_id", "offset"],
                f"{prefix}position.",
            ))

        # Dimensions validation
        if "dimensions" in cabinet:
            dims = cabinet["dimensions"]
            errors.extend(validate_required_fields(
                dims,
                ["width"],
                f"{prefix}dimensions.",
            ))

            # Dimensions must be positive
            for dim_name in ["width", "height", "depth"]:
                if dim_name in dims and dims[dim_name] <= 0:
                    errors.append(f"{prefix}dimensions.{dim_name} must be positive")

        # Configuration validation
        if "configuration" in cabinet:
            config = cabinet["configuration"]
            if "hinge_side" in config:
                errors.extend(validate_enum(
                    config["hinge_side"],
                    hinge_sides,
                    f"{prefix}configuration.hinge_side",
                ))

        # Style validation
        if "style" in cabinet:
            style = cabinet["style"]
            if "overlay_type" in style:
                errors.extend(validate_enum(
                    style["overlay_type"],
                    overlay_types,
                    f"{prefix}style.overlay_type",
                ))

    return errors


def validate_appliances(appliances: list[dict[str, Any]]) -> list[str]:
    """Validate appliances section."""
    errors = []

    appliance_types = [
        "range", "cooktop", "wall_oven", "microwave",
        "refrigerator", "dishwasher", "sink",
        "hood", "downdraft", "trash_compactor",
        "wine_cooler", "beverage_center",
    ]

    for i, appliance in enumerate(appliances):
        prefix = f"appliances[{i}]."

        # Required fields
        errors.extend(validate_required_fields(
            appliance,
            ["id", "appliance_type", "position", "dimensions"],
            prefix,
        ))

        # Appliance type enum
        if "appliance_type" in appliance:
            errors.extend(validate_enum(
                appliance["appliance_type"],
                appliance_types,
                f"{prefix}appliance_type",
            ))

    return errors


def validate_finishes(finishes: dict[str, Any]) -> list[str]:
    """Validate finishes section."""
    errors = []

    price_tiers = ["budget", "mid", "premium", "luxury"]

    if "packages" in finishes:
        for i, pkg in enumerate(finishes["packages"]):
            prefix = f"finishes.packages[{i}]."

            # Required fields
            errors.extend(validate_required_fields(
                pkg,
                ["id", "name"],
                prefix,
            ))

            if "price_tier" in pkg:
                errors.extend(validate_enum(
                    pkg["price_tier"],
                    price_tiers,
                    f"{prefix}price_tier",
                ))

    return errors


def validate_annotation(data: dict[str, Any]) -> list[str]:
    """
    Validate a complete annotation file.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Top-level required fields
    errors.extend(validate_required_fields(
        data,
        ["metadata", "room", "cabinets"],
        "",
    ))

    # Validate each section
    if "metadata" in data:
        errors.extend(validate_metadata(data["metadata"]))

    if "room" in data:
        errors.extend(validate_room(data["room"]))

    if "cabinets" in data:
        errors.extend(validate_cabinets(data["cabinets"]))

    if "appliances" in data:
        errors.extend(validate_appliances(data["appliances"]))

    if "finishes" in data:
        errors.extend(validate_finishes(data["finishes"]))

    return errors


def compute_completeness(data: dict[str, Any]) -> dict[str, float]:
    """Compute annotation completeness metrics."""
    metrics = {}

    # Metadata completeness
    if "metadata" in data:
        meta = data["metadata"]
        meta_fields = ["job_name", "client_name", "source_file", "source_type", "confidence_score"]
        metrics["metadata"] = sum(1 for f in meta_fields if f in meta and meta[f]) / len(meta_fields)
    else:
        metrics["metadata"] = 0.0

    # Room completeness
    if "room" in data:
        room = data["room"]
        has_walls = bool(room.get("walls"))
        has_openings = bool(room.get("openings"))
        has_ceiling = bool(room.get("ceiling_height"))
        metrics["room"] = sum([has_walls, has_openings, has_ceiling]) / 3
    else:
        metrics["room"] = 0.0

    # Cabinets completeness
    if "cabinets" in data and data["cabinets"]:
        cabinet_scores = []
        for cab in data["cabinets"]:
            has_config = bool(cab.get("configuration"))
            has_style = bool(cab.get("style"))
            has_dims = all(cab.get("dimensions", {}).get(d) for d in ["width", "height", "depth"])
            cabinet_scores.append(sum([has_config, has_style, has_dims]) / 3)
        metrics["cabinets"] = sum(cabinet_scores) / len(cabinet_scores) if cabinet_scores else 0.0
    else:
        metrics["cabinets"] = 0.0

    # Overall
    metrics["overall"] = sum(metrics.values()) / len(metrics)

    return metrics


def validate_file(file_path: Path, verbose: bool = False) -> tuple[bool, list[str], dict]:
    """
    Validate a single annotation file.

    Returns (is_valid, errors, completeness_metrics).
    """
    try:
        data = json.loads(file_path.read_text())
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"], {}

    errors = validate_annotation(data)
    completeness = compute_completeness(data)

    return len(errors) == 0, errors, completeness


def validate_directory(dir_path: Path, verbose: bool = False) -> dict[str, Any]:
    """
    Validate all annotation files in a directory.

    Returns summary statistics.
    """
    json_files = list(dir_path.glob("*.json"))

    results = {
        "total": len(json_files),
        "valid": 0,
        "invalid": 0,
        "errors": {},
        "completeness": {},
    }

    for json_file in json_files:
        is_valid, errors, completeness = validate_file(json_file, verbose)

        if is_valid:
            results["valid"] += 1
        else:
            results["invalid"] += 1
            results["errors"][str(json_file)] = errors

        results["completeness"][str(json_file)] = completeness

    # Compute average completeness
    if results["completeness"]:
        all_overall = [c.get("overall", 0) for c in results["completeness"].values()]
        results["avg_completeness"] = sum(all_overall) / len(all_overall)
    else:
        results["avg_completeness"] = 0.0

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate cabinet specification annotations"
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input directory containing annotation JSON files",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Single file to validate",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed validation errors",
    )

    args = parser.parse_args()

    if not args.input and not args.file:
        parser.print_help()
        sys.exit(1)

    if args.file:
        # Validate single file
        if not args.file.exists():
            console.print(f"[red]File not found: {args.file}[/red]")
            sys.exit(1)

        is_valid, errors, completeness = validate_file(args.file, args.verbose)

        if is_valid:
            console.print(f"[green]✓ {args.file} is valid[/green]")
        else:
            console.print(f"[red]✗ {args.file} has {len(errors)} errors:[/red]")
            for error in errors:
                console.print(f"  - {error}")

        console.print("\n[bold]Completeness:[/bold]")
        for key, value in completeness.items():
            console.print(f"  {key}: {value:.1%}")

        sys.exit(0 if is_valid else 1)

    if args.input:
        # Validate directory
        if not args.input.exists():
            console.print(f"[red]Directory not found: {args.input}[/red]")
            sys.exit(1)

        console.print(f"[bold]Validating annotations in {args.input}[/bold]\n")

        results = validate_directory(args.input, args.verbose)

        # Summary table
        table = Table(title="Validation Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value")

        table.add_row("Total files", str(results["total"]))
        table.add_row("Valid", f"[green]{results['valid']}[/green]")
        table.add_row("Invalid", f"[red]{results['invalid']}[/red]" if results["invalid"] else "0")
        table.add_row("Avg completeness", f"{results['avg_completeness']:.1%}")

        console.print(table)

        # Show errors if verbose
        if args.verbose and results["errors"]:
            console.print("\n[bold]Validation Errors:[/bold]")
            for file_path, errors in results["errors"].items():
                console.print(f"\n[yellow]{Path(file_path).name}:[/yellow]")
                for error in errors:
                    console.print(f"  - {error}")

        sys.exit(0 if results["invalid"] == 0 else 1)


if __name__ == "__main__":
    main()
