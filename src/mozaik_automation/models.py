"""
Pydantic models for cabinet design specifications.

These models define the data structures used throughout the pipeline,
matching the JSON schema defined in data/schemas/cabinet_spec.json.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, BeforeValidator, Field


# Enums
class Units(str, Enum):
    INCHES = "in"
    MILLIMETERS = "mm"
    CENTIMETERS = "cm"


class SourceType(str, Enum):
    FLOOR_PLAN = "floor_plan"
    ELEVATION = "elevation"
    SKETCH = "sketch"
    PHOTO = "photo"
    CAD = "cad"


class OpeningType(str, Enum):
    DOOR = "door"
    WINDOW = "window"
    PASS_THROUGH = "pass_through"
    ARCHWAY = "archway"


class CabinetType(str, Enum):
    BASE = "base"
    BASE_SINK = "base_sink"
    BASE_CORNER = "base_corner"
    BASE_BLIND_CORNER = "base_blind_corner"
    WALL = "wall"
    WALL_CORNER = "wall_corner"
    WALL_BLIND_CORNER = "wall_blind_corner"
    TALL = "tall"
    TALL_PANTRY = "tall_pantry"
    TALL_OVEN = "tall_oven"
    ISLAND = "island"
    PENINSULA = "peninsula"
    DRAWER_BASE = "drawer_base"
    APPLIANCE_GARAGE = "appliance_garage"
    OPEN_SHELF = "open_shelf"
    WINE_RACK = "wine_rack"


class HingeSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"
    NONE = "none"


class OverlayType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    INSET = "inset"


class ApplianceType(str, Enum):
    RANGE = "range"
    COOKTOP = "cooktop"
    WALL_OVEN = "wall_oven"
    MICROWAVE = "microwave"
    REFRIGERATOR = "refrigerator"
    DISHWASHER = "dishwasher"
    SINK = "sink"
    HOOD = "hood"
    DOWNDRAFT = "downdraft"
    TRASH_COMPACTOR = "trash_compactor"
    WINE_COOLER = "wine_cooler"
    BEVERAGE_CENTER = "beverage_center"


class PriceTier(str, Enum):
    BUDGET = "budget"
    MID = "mid"
    PREMIUM = "premium"
    LUXURY = "luxury"


# Component Models
def _coerce_point(v: Any) -> Any:
    """Coerce list to Point2D format."""
    if isinstance(v, list) and len(v) == 2:
        return {"x": v[0], "y": v[1]}
    return v


class Point2D(BaseModel):
    """2D point coordinate."""

    x: float
    y: float

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    @classmethod
    def from_list(cls, coords: list[float]) -> "Point2D":
        return cls(x=coords[0], y=coords[1])


# Type alias for Point2D that accepts lists
Point2DInput = Annotated[Point2D, BeforeValidator(_coerce_point)]


class Wall(BaseModel):
    """Wall segment in the room."""

    id: str
    start: Point2DInput
    end: Point2DInput
    thickness: float = 4.5

    @property
    def length(self) -> float:
        """Calculate wall length."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return (dx**2 + dy**2) ** 0.5


class Opening(BaseModel):
    """Door, window, or other opening in a wall."""

    id: Optional[str] = None
    type: OpeningType
    wall_id: str
    offset: float = Field(..., description="Distance from wall start to opening center")
    width: float
    height: float
    sill_height: Optional[float] = Field(
        None, description="Height from floor to bottom of opening"
    )


class Dimensions(BaseModel):
    """Cabinet or appliance dimensions."""

    width: float
    height: Optional[float] = None
    depth: Optional[float] = None


class Position(BaseModel):
    """Position specification for a cabinet or appliance."""

    wall_id: str = Field(..., description="Reference to wall ID, or 'ISLAND' for freestanding")
    offset: float = Field(..., description="Distance from wall start to cabinet left edge")
    elevation: float = Field(0, description="Height from floor to cabinet bottom")


class CabinetConfiguration(BaseModel):
    """Cabinet interior configuration."""

    door_count: int = 1
    drawer_count: int = 0
    hinge_side: Optional[HingeSide] = None
    shelf_count: Optional[int] = None
    has_rollout: bool = False
    has_lazy_susan: bool = False


class CabinetStyle(BaseModel):
    """Cabinet style and finish."""

    door_style: Optional[str] = None
    finish_package: Optional[str] = None
    overlay_type: Optional[OverlayType] = None


class Cabinet(BaseModel):
    """Single cabinet unit."""

    id: str
    cabinet_type: CabinetType
    position: Position
    dimensions: Dimensions
    configuration: Optional[CabinetConfiguration] = None
    style: Optional[CabinetStyle] = None
    notes: Optional[str] = None


class Appliance(BaseModel):
    """Appliance placement."""

    id: str
    appliance_type: ApplianceType
    position: Position
    dimensions: Dimensions
    model: Optional[str] = None
    brand: Optional[str] = None


class FinishPackage(BaseModel):
    """Predefined finish combination."""

    id: str
    name: str
    description: Optional[str] = None
    door_style: Optional[str] = None
    door_material: Optional[str] = None
    door_color: Optional[str] = None
    box_material: Optional[str] = None
    box_color: Optional[str] = None
    hardware_style: Optional[str] = None
    hardware_finish: Optional[str] = None
    countertop_material: Optional[str] = None
    countertop_color: Optional[str] = None
    price_tier: Optional[PriceTier] = None


class Finishes(BaseModel):
    """Material and finish specifications."""

    packages: list[FinishPackage] = []
    default_package: Optional[str] = None


class CrownMolding(BaseModel):
    """Crown molding specification."""

    style: Optional[str] = None
    height: Optional[float] = None
    locations: list[str] = []


class LightRail(BaseModel):
    """Light rail specification."""

    style: Optional[str] = None
    height: Optional[float] = None


class ToeKick(BaseModel):
    """Toe kick specification."""

    height: float = 4
    material: Optional[str] = None


class Filler(BaseModel):
    """Filler strip specification."""

    location: str
    width: float


class Trim(BaseModel):
    """Trim and molding specifications."""

    crown_molding: Optional[CrownMolding] = None
    light_rail: Optional[LightRail] = None
    toe_kick: Optional[ToeKick] = None
    fillers: list[Filler] = []


class ShopRules(BaseModel):
    """Shop-specific construction rules."""

    min_filler_width: float = 1.5
    max_filler_width: float = 6
    standard_base_height: float = 34.5
    standard_wall_height: float = 30
    standard_depth_base: float = 24
    standard_depth_wall: float = 12
    corner_cabinet_dead_space: float = 3


class Room(BaseModel):
    """Room geometry and layout."""

    name: str = "Kitchen"
    units: Units = Units.INCHES
    ceiling_height: float
    walls: list[Wall]
    openings: list[Opening] = []


class Metadata(BaseModel):
    """Job metadata and source information."""

    job_name: str
    client_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    source_file: Optional[str] = None
    source_type: Optional[SourceType] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=1)
    notes: Optional[str] = None


class CabinetSpec(BaseModel):
    """Complete cabinet design specification."""

    metadata: Metadata
    room: Room
    cabinets: list[Cabinet]
    appliances: list[Appliance] = []
    finishes: Optional[Finishes] = None
    trim: Optional[Trim] = None
    shop_rules: Optional[ShopRules] = None

    def to_json(self, indent: int = 2) -> str:
        """Export to JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "CabinetSpec":
        """Import from JSON string."""
        return cls.model_validate_json(json_str)

    def get_cabinet_by_id(self, cabinet_id: str) -> Optional[Cabinet]:
        """Find a cabinet by its ID."""
        for cab in self.cabinets:
            if cab.id == cabinet_id:
                return cab
        return None

    def get_cabinets_on_wall(self, wall_id: str) -> list[Cabinet]:
        """Get all cabinets on a specific wall."""
        return [c for c in self.cabinets if c.position.wall_id == wall_id]

    def total_linear_feet(self) -> float:
        """Calculate total linear feet of cabinets."""
        total_inches = sum(c.dimensions.width for c in self.cabinets)
        return total_inches / 12
