"""
Mozaik Automation - AI-powered cabinet design assistant.

This package provides tools for:
- Extracting room and cabinet specifications from drawings using vision models
- Generating DXF files for Mozaik import
- Creating operator checklists and automation scripts
- UI automation for Mozaik software
"""

__version__ = "0.1.0"

# Lazy imports to avoid loading heavy dependencies for server-only use
def __getattr__(name):
    if name == "CabinetSpec":
        from mozaik_automation.models import CabinetSpec
        return CabinetSpec
    if name == "Room":
        from mozaik_automation.models import Room
        return Room
    if name == "Cabinet":
        from mozaik_automation.models import Cabinet
        return Cabinet
    if name == "Appliance":
        from mozaik_automation.models import Appliance
        return Appliance
    if name == "CabinetVisionPipeline":
        from mozaik_automation.pipeline import CabinetVisionPipeline
        return CabinetVisionPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CabinetSpec",
    "Room",
    "Cabinet",
    "Appliance",
    "CabinetVisionPipeline",
]
