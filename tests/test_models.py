"""
Tests for Pydantic models.

TDD: These tests define the expected behavior of our data models.
"""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from mozaik_automation.models import (
    Cabinet,
    CabinetConfiguration,
    CabinetSpec,
    CabinetStyle,
    CabinetType,
    Dimensions,
    FinishPackage,
    Finishes,
    HingeSide,
    Metadata,
    Opening,
    OpeningType,
    OverlayType,
    Point2D,
    Position,
    PriceTier,
    Room,
    ShopRules,
    SourceType,
    Trim,
    Units,
    Wall,
)


class TestPoint2D:
    """Tests for Point2D model."""

    def test_create_point(self):
        """Should create a point with x and y coordinates."""
        point = Point2D(x=10.5, y=20.3)
        assert point.x == 10.5
        assert point.y == 20.3

    def test_to_tuple(self):
        """Should convert to tuple for DXF compatibility."""
        point = Point2D(x=5, y=10)
        assert point.to_tuple() == (5, 10)

    def test_from_list(self):
        """Should create from list format (JSON compatibility)."""
        point = Point2D.from_list([15.5, 25.5])
        assert point.x == 15.5
        assert point.y == 25.5


class TestWall:
    """Tests for Wall model."""

    def test_create_wall(self, sample_wall):
        """Should create a wall with start, end, and thickness."""
        assert sample_wall.id == "W1"
        assert sample_wall.start.x == 0
        assert sample_wall.end.x == 156
        assert sample_wall.thickness == 4.5

    def test_wall_length(self):
        """Should calculate wall length correctly."""
        # Horizontal wall
        wall = Wall(
            id="W1",
            start=Point2D(x=0, y=0),
            end=Point2D(x=100, y=0),
        )
        assert wall.length == 100

        # Diagonal wall (3-4-5 triangle)
        wall_diag = Wall(
            id="W2",
            start=Point2D(x=0, y=0),
            end=Point2D(x=3, y=4),
        )
        assert wall_diag.length == 5

    def test_default_thickness(self):
        """Should use default wall thickness of 4.5 inches."""
        wall = Wall(
            id="W1",
            start=Point2D(x=0, y=0),
            end=Point2D(x=100, y=0),
        )
        assert wall.thickness == 4.5


class TestOpening:
    """Tests for Opening model."""

    def test_create_window(self, sample_opening):
        """Should create a window opening."""
        assert sample_opening.type == OpeningType.WINDOW
        assert sample_opening.wall_id == "W1"
        assert sample_opening.width == 36
        assert sample_opening.height == 48
        assert sample_opening.sill_height == 42

    def test_create_door(self):
        """Should create a door opening."""
        door = Opening(
            type=OpeningType.DOOR,
            wall_id="W2",
            offset=36,
            width=36,
            height=80,
            sill_height=0,
        )
        assert door.type == OpeningType.DOOR
        assert door.sill_height == 0


class TestDimensions:
    """Tests for Dimensions model."""

    def test_width_required(self):
        """Width should be required."""
        dims = Dimensions(width=24)
        assert dims.width == 24
        assert dims.height is None
        assert dims.depth is None

    def test_all_dimensions(self):
        """Should store all dimensions."""
        dims = Dimensions(width=24, height=34.5, depth=24)
        assert dims.width == 24
        assert dims.height == 34.5
        assert dims.depth == 24


class TestCabinet:
    """Tests for Cabinet model."""

    def test_create_base_cabinet(self, sample_cabinet):
        """Should create a base cabinet with all properties."""
        assert sample_cabinet.id == "B1"
        assert sample_cabinet.cabinet_type == CabinetType.BASE
        assert sample_cabinet.position.wall_id == "W1"
        assert sample_cabinet.dimensions.width == 24

    def test_cabinet_configuration(self, sample_cabinet):
        """Should include configuration details."""
        config = sample_cabinet.configuration
        assert config.door_count == 1
        assert config.drawer_count == 1
        assert config.hinge_side == HingeSide.LEFT

    def test_cabinet_style(self, sample_cabinet):
        """Should include style details."""
        style = sample_cabinet.style
        assert style.door_style == "SHAKER"
        assert style.overlay_type == OverlayType.FULL

    def test_all_cabinet_types(self):
        """All cabinet types should be valid."""
        for cab_type in CabinetType:
            cab = Cabinet(
                id="TEST",
                cabinet_type=cab_type,
                position=Position(wall_id="W1", offset=0),
                dimensions=Dimensions(width=24),
            )
            assert cab.cabinet_type == cab_type


class TestRoom:
    """Tests for Room model."""

    def test_create_room(self, sample_room):
        """Should create a room with walls and openings."""
        assert sample_room.name == "Test Kitchen"
        assert sample_room.units == Units.INCHES
        assert sample_room.ceiling_height == 96
        assert len(sample_room.walls) == 4
        assert len(sample_room.openings) == 1

    def test_default_name(self):
        """Should default to 'Kitchen'."""
        room = Room(
            units=Units.INCHES,
            ceiling_height=96,
            walls=[],
        )
        assert room.name == "Kitchen"


class TestFinishPackage:
    """Tests for FinishPackage model."""

    def test_create_finish_package(self, sample_finish_package):
        """Should create a complete finish package."""
        pkg = sample_finish_package
        assert pkg.id == "PKG_MODERN_WHITE"
        assert pkg.name == "Modern White & Walnut"
        assert pkg.price_tier == PriceTier.PREMIUM

    def test_all_price_tiers(self):
        """All price tiers should be valid."""
        for tier in PriceTier:
            pkg = FinishPackage(id="TEST", name="Test", price_tier=tier)
            assert pkg.price_tier == tier


class TestCabinetSpec:
    """Tests for CabinetSpec model."""

    def test_create_complete_spec(self, sample_cabinet_spec):
        """Should create a complete cabinet specification."""
        spec = sample_cabinet_spec
        assert spec.metadata.job_name == "Test Job 001"
        assert spec.room.name == "Test Kitchen"
        assert len(spec.cabinets) == 5

    def test_to_json(self, sample_cabinet_spec):
        """Should serialize to JSON."""
        json_str = sample_cabinet_spec.to_json()
        data = json.loads(json_str)
        assert data["metadata"]["job_name"] == "Test Job 001"
        assert len(data["cabinets"]) == 5

    def test_from_json(self, sample_spec_json):
        """Should deserialize from JSON."""
        spec = CabinetSpec.from_json(sample_spec_json)
        assert spec.metadata.job_name == "Test Job 001"
        assert len(spec.cabinets) == 5

    def test_get_cabinet_by_id(self, sample_cabinet_spec):
        """Should find cabinet by ID."""
        cab = sample_cabinet_spec.get_cabinet_by_id("B2")
        assert cab is not None
        assert cab.cabinet_type == CabinetType.BASE_SINK

    def test_get_cabinet_by_id_not_found(self, sample_cabinet_spec):
        """Should return None for non-existent ID."""
        cab = sample_cabinet_spec.get_cabinet_by_id("NONEXISTENT")
        assert cab is None

    def test_get_cabinets_on_wall(self, sample_cabinet_spec):
        """Should filter cabinets by wall."""
        cabs = sample_cabinet_spec.get_cabinets_on_wall("W1")
        assert len(cabs) == 5  # All sample cabinets are on W1

    def test_total_linear_feet(self, sample_cabinet_spec):
        """Should calculate total linear feet."""
        lf = sample_cabinet_spec.total_linear_feet()
        # B1(24) + B2(36) + B3(24) + U1(24) + U2(24) = 132 inches = 11 LF
        assert lf == 11.0


class TestMetadata:
    """Tests for Metadata model."""

    def test_create_metadata(self, sample_metadata):
        """Should create metadata with all fields."""
        assert sample_metadata.job_name == "Test Job 001"
        assert sample_metadata.confidence_score == 0.95
        assert sample_metadata.source_type == SourceType.FLOOR_PLAN

    def test_confidence_score_validation(self):
        """Confidence score should be between 0 and 1."""
        # Valid scores
        meta = Metadata(job_name="Test", confidence_score=0.5)
        assert meta.confidence_score == 0.5

        # Invalid scores should raise
        with pytest.raises(ValidationError):
            Metadata(job_name="Test", confidence_score=1.5)

        with pytest.raises(ValidationError):
            Metadata(job_name="Test", confidence_score=-0.1)

    def test_auto_created_at(self):
        """Should auto-generate created_at timestamp."""
        meta = Metadata(job_name="Test")
        assert meta.created_at is not None
        assert isinstance(meta.created_at, datetime)


class TestShopRules:
    """Tests for ShopRules model."""

    def test_default_values(self):
        """Should have sensible defaults."""
        rules = ShopRules()
        assert rules.standard_base_height == 34.5
        assert rules.standard_wall_height == 30
        assert rules.standard_depth_base == 24
        assert rules.standard_depth_wall == 12
        assert rules.min_filler_width == 1.5

    def test_custom_values(self):
        """Should accept custom shop rules."""
        rules = ShopRules(
            standard_base_height=36,
            min_filler_width=2,
        )
        assert rules.standard_base_height == 36
        assert rules.min_filler_width == 2
