"""
General-purpose layers extracted from the Mozaik automation project.

This package provides:
- A Win32 control layer: a cached-element driver for Windows desktop applications
  (`mozaik_automation.automation`)
- Drawing-to-specification extraction with vision models (`mozaik_automation.vision`)
  against a typed specification schema (`mozaik_automation.models`)
- Deterministic, code-enforced verification of a build against its specification
  (`mozaik_automation.verification`)

The cabinetry product built on these layers (DXF output, checklists, finish engine,
the build pipeline, element caches and trained models) is not part of this package.
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CabinetSpec",
    "Room",
    "Cabinet",
    "Appliance",
]
