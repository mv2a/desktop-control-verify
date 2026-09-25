"""Every package module imports, on any OS, without reaching for code that was not extracted.

The private project this repository was extracted from also held a cabinetry pipeline,
DXF output, an LLM finish engine, a licensing client, a server and training code. None of
those modules exist here, and this test fails if anything tries to import them.
"""

import importlib
import pkgutil
import sys

import pytest

import mozaik_automation

NOT_EXTRACTED = (
    "mozaik_automation.pipeline",
    "mozaik_automation.cli",
    "mozaik_automation.parametric_spec",
    "mozaik_automation.dxf",
    "mozaik_automation.llm",
    "mozaik_automation.licensing",
    "mozaik_automation.server",
    "mozaik_automation.training",
    "mozaik_automation.automation.mozaik_driver",
    "mozaik_automation.automation.design_handler",
    "mozaik_automation.automation.mock_mozaik",
)

MODULES = sorted(
    m.name for m in pkgutil.walk_packages(mozaik_automation.__path__, "mozaik_automation.")
)


def test_expected_modules_are_present():
    for name in (
        "mozaik_automation.models",
        "mozaik_automation.automation.fast_driver",
        "mozaik_automation.vision.extractor",
        "mozaik_automation.verification.comparator",
        "mozaik_automation.verification.build_steps",
    ):
        assert name in MODULES


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)


def test_no_module_that_was_not_extracted_is_loaded():
    for name in MODULES:
        importlib.import_module(name)
    loaded = [m for m in sys.modules if m.startswith(NOT_EXTRACTED)]
    assert loaded == []
    for name in NOT_EXTRACTED:
        assert name not in MODULES


def test_lazy_exports_resolve():
    import mozaik_automation.automation as automation

    assert automation.CachedWin32Driver is automation.FastMozaikDriver
    assert mozaik_automation.CabinetSpec.__name__ == "CabinetSpec"
    with pytest.raises(AttributeError):
        mozaik_automation.CabinetVisionPipeline  # noqa: B018
