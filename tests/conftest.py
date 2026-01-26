"""
Pytest configuration and fixtures for mozaik-automation tests.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

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
    SourceType,
    Units,
    Wall,
)


@pytest.fixture
def sample_wall() -> Wall:
    """Create a sample wall."""
    return Wall(
        id="W1",
        start=Point2D(x=0, y=0),
        end=Point2D(x=156, y=0),
        thickness=4.5,
    )


@pytest.fixture
def sample_walls() -> list[Wall]:
    """Create a typical L-shaped kitchen wall layout."""
    return [
        Wall(id="W1", start=Point2D(x=0, y=0), end=Point2D(x=156, y=0)),
        Wall(id="W2", start=Point2D(x=156, y=0), end=Point2D(x=156, y=144)),
        Wall(id="W3", start=Point2D(x=156, y=144), end=Point2D(x=0, y=144)),
        Wall(id="W4", start=Point2D(x=0, y=144), end=Point2D(x=0, y=0)),
    ]


@pytest.fixture
def sample_opening() -> Opening:
    """Create a sample window opening."""
    return Opening(
        id="O1",
        type=OpeningType.WINDOW,
        wall_id="W1",
        offset=78,  # Center of 156" wall
        width=36,
        height=48,
        sill_height=42,
    )


@pytest.fixture
def sample_room(sample_walls, sample_opening) -> Room:
    """Create a sample room."""
    return Room(
        name="Test Kitchen",
        units=Units.INCHES,
        ceiling_height=96,
        walls=sample_walls,
        openings=[sample_opening],
    )


@pytest.fixture
def sample_cabinet() -> Cabinet:
    """Create a sample base cabinet."""
    return Cabinet(
        id="B1",
        cabinet_type=CabinetType.BASE,
        position=Position(wall_id="W1", offset=0, elevation=0),
        dimensions=Dimensions(width=24, height=34.5, depth=24),
        configuration=CabinetConfiguration(
            door_count=1,
            drawer_count=1,
            hinge_side=HingeSide.LEFT,
        ),
        style=CabinetStyle(
            door_style="SHAKER",
            finish_package="PKG_WHITE",
            overlay_type=OverlayType.FULL,
        ),
    )


@pytest.fixture
def sample_cabinets() -> list[Cabinet]:
    """Create a set of sample cabinets for a wall run."""
    return [
        Cabinet(
            id="B1",
            cabinet_type=CabinetType.BASE,
            position=Position(wall_id="W1", offset=0),
            dimensions=Dimensions(width=24, height=34.5, depth=24),
        ),
        Cabinet(
            id="B2",
            cabinet_type=CabinetType.BASE_SINK,
            position=Position(wall_id="W1", offset=24),
            dimensions=Dimensions(width=36, height=34.5, depth=24),
        ),
        Cabinet(
            id="B3",
            cabinet_type=CabinetType.BASE,
            position=Position(wall_id="W1", offset=60),
            dimensions=Dimensions(width=24, height=34.5, depth=24),
        ),
        Cabinet(
            id="U1",
            cabinet_type=CabinetType.WALL,
            position=Position(wall_id="W1", offset=0, elevation=54),
            dimensions=Dimensions(width=24, height=30, depth=12),
        ),
        Cabinet(
            id="U2",
            cabinet_type=CabinetType.WALL,
            position=Position(wall_id="W1", offset=60, elevation=54),
            dimensions=Dimensions(width=24, height=30, depth=12),
        ),
    ]


@pytest.fixture
def sample_finish_package() -> FinishPackage:
    """Create a sample finish package."""
    return FinishPackage(
        id="PKG_MODERN_WHITE",
        name="Modern White & Walnut",
        description="Clean white cabinets with warm walnut accents",
        door_style="Shaker",
        door_material="MDF",
        door_color="White",
        box_material="Melamine",
        box_color="White",
        hardware_style="Bar Pull",
        hardware_finish="Brushed Brass",
        countertop_material="Quartz",
        countertop_color="Calacatta",
        price_tier=PriceTier.PREMIUM,
    )


@pytest.fixture
def sample_metadata() -> Metadata:
    """Create sample job metadata."""
    return Metadata(
        job_name="Test Job 001",
        client_name="Test Client",
        created_at=datetime(2024, 1, 15, 10, 30),
        source_file="test_floor_plan.pdf",
        source_type=SourceType.FLOOR_PLAN,
        confidence_score=0.95,
    )


@pytest.fixture
def sample_cabinet_spec(
    sample_metadata, sample_room, sample_cabinets, sample_finish_package
) -> CabinetSpec:
    """Create a complete sample cabinet specification."""
    return CabinetSpec(
        metadata=sample_metadata,
        room=sample_room,
        cabinets=sample_cabinets,
        appliances=[],
        finishes=Finishes(
            packages=[sample_finish_package],
            default_package="PKG_MODERN_WHITE",
        ),
    )


@pytest.fixture
def sample_spec_json(sample_cabinet_spec) -> str:
    """Get sample spec as JSON string."""
    return sample_cabinet_spec.to_json()


@pytest.fixture
def temp_output_dir(tmp_path) -> Path:
    """Create temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def materials_database() -> dict:
    """Sample materials database for testing."""
    return {
        "door_styles": [
            {"id": "SHAKER", "name": "Shaker", "price_tier": "mid"},
            {"id": "FLAT", "name": "Slab/Flat", "price_tier": "budget"},
            {"id": "RAISED", "name": "Raised Panel", "price_tier": "premium"},
        ],
        "door_colors": [
            {"id": "WHITE", "name": "Pure White", "hex": "#FFFFFF"},
            {"id": "GRAY", "name": "Dove Gray", "hex": "#6B7280"},
            {"id": "NAVY", "name": "Navy Blue", "hex": "#1E3A5F"},
        ],
        "box_materials": [
            {"id": "MEL_WHITE", "name": "White Melamine"},
            {"id": "PLY_BIRCH", "name": "Birch Plywood"},
        ],
        "hardware": [
            {"id": "BAR_BRASS", "name": "Bar Pull - Brass"},
            {"id": "BAR_BLACK", "name": "Bar Pull - Matte Black"},
            {"id": "KNOB_CHROME", "name": "Round Knob - Chrome"},
        ],
        "countertops": [
            {"id": "QUARTZ_CAL", "name": "Calacatta Quartz"},
            {"id": "GRANITE_BLK", "name": "Black Granite"},
            {"id": "BUTCHER", "name": "Butcher Block"},
        ],
    }
