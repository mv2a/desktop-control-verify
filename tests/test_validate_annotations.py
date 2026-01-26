"""Tests for annotation validation script."""

import json
import tempfile
from pathlib import Path

import pytest

# Import functions from script
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from validate_annotations import (
    validate_annotation,
    validate_metadata,
    validate_room,
    validate_cabinets,
    validate_appliances,
    validate_finishes,
    compute_completeness,
    validate_required_fields,
    validate_enum,
    validate_number_range,
)


class TestValidationHelpers:
    """Tests for validation helper functions."""

    def test_validate_required_fields_success(self):
        """Should pass when all required fields present."""
        data = {"a": 1, "b": 2, "c": 3}
        errors = validate_required_fields(data, ["a", "b"], "test.")
        assert len(errors) == 0

    def test_validate_required_fields_missing(self):
        """Should report missing required fields."""
        data = {"a": 1}
        errors = validate_required_fields(data, ["a", "b"], "test.")
        assert len(errors) == 1
        assert "test.b" in errors[0]

    def test_validate_enum_success(self):
        """Should pass for valid enum value."""
        errors = validate_enum("foo", ["foo", "bar"], "field")
        assert len(errors) == 0

    def test_validate_enum_failure(self):
        """Should fail for invalid enum value."""
        errors = validate_enum("baz", ["foo", "bar"], "field")
        assert len(errors) == 1
        assert "baz" in errors[0]

    def test_validate_number_range_success(self):
        """Should pass for number in range."""
        errors = validate_number_range(0.5, 0.0, 1.0, "field")
        assert len(errors) == 0

    def test_validate_number_range_below_min(self):
        """Should fail for number below minimum."""
        errors = validate_number_range(-0.1, 0.0, 1.0, "field")
        assert len(errors) == 1
        assert ">=" in errors[0]

    def test_validate_number_range_above_max(self):
        """Should fail for number above maximum."""
        errors = validate_number_range(1.5, 0.0, 1.0, "field")
        assert len(errors) == 1
        assert "<=" in errors[0]


class TestMetadataValidation:
    """Tests for metadata validation."""

    def test_valid_metadata(self):
        """Should pass for complete metadata."""
        metadata = {
            "job_name": "Test Job",
            "source_type": "floor_plan",
            "confidence_score": 0.95,
        }
        errors = validate_metadata(metadata)
        assert len(errors) == 0

    def test_missing_job_name(self):
        """Should fail when job_name missing."""
        metadata = {"source_type": "floor_plan"}
        errors = validate_metadata(metadata)
        assert any("job_name" in e for e in errors)

    def test_invalid_source_type(self):
        """Should fail for invalid source_type."""
        metadata = {"job_name": "Test", "source_type": "invalid"}
        errors = validate_metadata(metadata)
        assert any("source_type" in e for e in errors)

    def test_invalid_confidence_score(self):
        """Should fail for out-of-range confidence."""
        metadata = {"job_name": "Test", "confidence_score": 1.5}
        errors = validate_metadata(metadata)
        assert any("confidence_score" in e for e in errors)


class TestRoomValidation:
    """Tests for room validation."""

    def test_valid_room(self):
        """Should pass for complete room."""
        room = {
            "units": "in",
            "ceiling_height": 96,
            "walls": [
                {"id": "W1", "start": [0, 0], "end": [100, 0]},
            ],
            "openings": [
                {"type": "door", "wall_id": "W1", "offset": 50, "width": 36, "height": 80},
            ],
        }
        errors = validate_room(room)
        assert len(errors) == 0

    def test_missing_units(self):
        """Should fail when units missing."""
        room = {"ceiling_height": 96, "walls": []}
        errors = validate_room(room)
        assert any("units" in e for e in errors)

    def test_invalid_units(self):
        """Should fail for invalid units."""
        room = {"units": "feet", "ceiling_height": 96, "walls": []}
        errors = validate_room(room)
        assert any("units" in e for e in errors)

    def test_invalid_ceiling_height(self):
        """Should fail for non-positive ceiling height."""
        room = {"units": "in", "ceiling_height": 0, "walls": []}
        errors = validate_room(room)
        assert any("ceiling_height" in e for e in errors)

    def test_wall_missing_id(self):
        """Should fail when wall missing id."""
        room = {
            "units": "in",
            "ceiling_height": 96,
            "walls": [{"start": [0, 0], "end": [100, 0]}],
        }
        errors = validate_room(room)
        assert any("walls[0].id" in e for e in errors)

    def test_invalid_opening_type(self):
        """Should fail for invalid opening type."""
        room = {
            "units": "in",
            "ceiling_height": 96,
            "walls": [],
            "openings": [
                {"type": "invalid", "wall_id": "W1", "offset": 0, "width": 36, "height": 80},
            ],
        }
        errors = validate_room(room)
        assert any("type" in e for e in errors)


class TestCabinetValidation:
    """Tests for cabinet validation."""

    def test_valid_cabinet(self):
        """Should pass for complete cabinet."""
        cabinets = [{
            "id": "B1",
            "cabinet_type": "base",
            "position": {"wall_id": "W1", "offset": 0},
            "dimensions": {"width": 24, "height": 34.5, "depth": 24},
            "configuration": {"hinge_side": "left"},
            "style": {"overlay_type": "full"},
        }]
        errors = validate_cabinets(cabinets)
        assert len(errors) == 0

    def test_invalid_cabinet_type(self):
        """Should fail for invalid cabinet type."""
        cabinets = [{
            "id": "B1",
            "cabinet_type": "invalid_type",
            "position": {"wall_id": "W1", "offset": 0},
            "dimensions": {"width": 24},
        }]
        errors = validate_cabinets(cabinets)
        assert any("cabinet_type" in e for e in errors)

    def test_missing_position(self):
        """Should fail when position missing."""
        cabinets = [{
            "id": "B1",
            "cabinet_type": "base",
            "dimensions": {"width": 24},
        }]
        errors = validate_cabinets(cabinets)
        assert any("position" in e for e in errors)

    def test_negative_dimension(self):
        """Should fail for negative dimensions."""
        cabinets = [{
            "id": "B1",
            "cabinet_type": "base",
            "position": {"wall_id": "W1", "offset": 0},
            "dimensions": {"width": -10},
        }]
        errors = validate_cabinets(cabinets)
        assert any("width" in e and "positive" in e for e in errors)

    def test_invalid_hinge_side(self):
        """Should fail for invalid hinge side."""
        cabinets = [{
            "id": "B1",
            "cabinet_type": "base",
            "position": {"wall_id": "W1", "offset": 0},
            "dimensions": {"width": 24},
            "configuration": {"hinge_side": "top"},
        }]
        errors = validate_cabinets(cabinets)
        assert any("hinge_side" in e for e in errors)


class TestApplianceValidation:
    """Tests for appliance validation."""

    def test_valid_appliance(self):
        """Should pass for complete appliance."""
        appliances = [{
            "id": "A1",
            "appliance_type": "range",
            "position": {"wall_id": "W1", "offset": 0},
            "dimensions": {"width": 30},
        }]
        errors = validate_appliances(appliances)
        assert len(errors) == 0

    def test_invalid_appliance_type(self):
        """Should fail for invalid appliance type."""
        appliances = [{
            "id": "A1",
            "appliance_type": "toaster",
            "position": {"wall_id": "W1", "offset": 0},
            "dimensions": {"width": 12},
        }]
        errors = validate_appliances(appliances)
        assert any("appliance_type" in e for e in errors)


class TestFinishesValidation:
    """Tests for finishes validation."""

    def test_valid_finishes(self):
        """Should pass for complete finishes."""
        finishes = {
            "packages": [
                {"id": "PKG1", "name": "Modern", "price_tier": "mid"},
            ],
        }
        errors = validate_finishes(finishes)
        assert len(errors) == 0

    def test_invalid_price_tier(self):
        """Should fail for invalid price tier."""
        finishes = {
            "packages": [
                {"id": "PKG1", "name": "Modern", "price_tier": "expensive"},
            ],
        }
        errors = validate_finishes(finishes)
        assert any("price_tier" in e for e in errors)


class TestCompleteValidation:
    """Tests for complete annotation validation."""

    def test_valid_annotation(self):
        """Should pass for complete valid annotation."""
        data = {
            "metadata": {"job_name": "Test"},
            "room": {
                "units": "in",
                "ceiling_height": 96,
                "walls": [{"id": "W1", "start": [0, 0], "end": [100, 0]}],
            },
            "cabinets": [{
                "id": "B1",
                "cabinet_type": "base",
                "position": {"wall_id": "W1", "offset": 0},
                "dimensions": {"width": 24},
            }],
        }
        errors = validate_annotation(data)
        assert len(errors) == 0

    def test_missing_top_level(self):
        """Should fail when top-level sections missing."""
        data = {"metadata": {"job_name": "Test"}}
        errors = validate_annotation(data)
        assert any("room" in e for e in errors)
        assert any("cabinets" in e for e in errors)


class TestCompleteness:
    """Tests for completeness metrics."""

    def test_full_completeness(self):
        """Should compute 100% for complete annotation."""
        data = {
            "metadata": {
                "job_name": "Test",
                "client_name": "Client",
                "source_file": "test.png",
                "source_type": "floor_plan",
                "confidence_score": 0.95,
            },
            "room": {
                "ceiling_height": 96,
                "walls": [{"id": "W1"}],
                "openings": [{"id": "O1"}],
            },
            "cabinets": [{
                "configuration": {"doors": 1},
                "style": {"door_style": "shaker"},
                "dimensions": {"width": 24, "height": 34.5, "depth": 24},
            }],
        }
        metrics = compute_completeness(data)
        assert metrics["metadata"] == 1.0
        assert metrics["room"] == 1.0
        assert metrics["cabinets"] == 1.0

    def test_partial_completeness(self):
        """Should compute partial completeness for incomplete annotation."""
        data = {
            "metadata": {"job_name": "Test"},
            "room": {"walls": []},
            "cabinets": [],
        }
        metrics = compute_completeness(data)
        assert metrics["metadata"] < 1.0
        assert metrics["room"] < 1.0
        assert metrics["cabinets"] == 0.0

    def test_empty_data(self):
        """Should handle empty data."""
        metrics = compute_completeness({})
        assert metrics["metadata"] == 0.0
        assert metrics["room"] == 0.0
        assert metrics["cabinets"] == 0.0
