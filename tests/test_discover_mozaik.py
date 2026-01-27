"""
Tests for discover_mozaik_ui.py discovery logic.

Tests parsing, reporting, and element comparison against ElementMapping
without requiring pywinauto or a running Mozaik instance.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the discovery module's data structures and functions
# We import from the scripts directory
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from discover_mozaik_ui import (
    DEFAULT_ELEMENT_MAPPING,
    DiscoveryReport,
    MappingMatch,
    UIElement,
    build_report,
    compare_mapping,
    enumerate_elements,
    _extract_element_info,
    _find_matching_element,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_elements() -> list[UIElement]:
    """A realistic set of discovered UI elements."""
    return [
        UIElement(
            name="File",
            control_type="MenuItem",
            automation_id="",
            class_name="MenuItemControl",
            depth=0,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="New Room",
            control_type="MenuItem",
            automation_id="",
            class_name="MenuItemControl",
            depth=1,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="Wall",
            control_type="Button",
            automation_id="btnWall",
            class_name="ButtonControl",
            depth=0,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="Opening",
            control_type="Button",
            automation_id="btnOpening",
            class_name="ButtonControl",
            depth=0,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="Cabinet",
            control_type="Button",
            automation_id="btnCabinet",
            class_name="ButtonControl",
            depth=0,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="OK",
            control_type="Button",
            automation_id="btnOK",
            class_name="ButtonControl",
            depth=2,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="Cancel",
            control_type="Button",
            automation_id="btnCancel",
            class_name="ButtonControl",
            depth=2,
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            name="",
            control_type="Custom",
            automation_id="designCanvas",
            class_name="DesignCanvasControl",
            depth=0,
            is_enabled=True,
            is_visible=True,
            rectangle={"left": 0, "top": 0, "right": 1920, "bottom": 1080},
        ),
    ]


@pytest.fixture
def empty_elements() -> list[UIElement]:
    """Empty element list."""
    return []


# ---------------------------------------------------------------------------
# UIElement tests
# ---------------------------------------------------------------------------

class TestUIElement:
    """Tests for UIElement data structure."""

    def test_default_values(self):
        elem = UIElement()
        assert elem.name == ""
        assert elem.automation_id == ""
        assert elem.control_type == ""
        assert elem.class_name == ""
        assert elem.rectangle is None
        assert elem.depth == 0
        assert elem.children_count == 0
        assert elem.is_enabled is True
        assert elem.is_visible is True

    def test_to_dict(self):
        elem = UIElement(
            name="OK",
            control_type="Button",
            automation_id="btnOK",
            class_name="ButtonControl",
            depth=1,
            children_count=0,
            is_enabled=True,
            is_visible=True,
        )
        d = elem.to_dict()
        assert d["name"] == "OK"
        assert d["control_type"] == "Button"
        assert d["automation_id"] == "btnOK"
        assert d["class_name"] == "ButtonControl"
        assert d["depth"] == 1
        assert "rectangle" not in d

    def test_to_dict_with_rectangle(self):
        elem = UIElement(
            name="Canvas",
            rectangle={"left": 10, "top": 20, "right": 100, "bottom": 200},
        )
        d = elem.to_dict()
        assert d["rectangle"] == {"left": 10, "top": 20, "right": 100, "bottom": 200}

    def test_to_dict_without_rectangle(self):
        elem = UIElement(name="NoRect")
        d = elem.to_dict()
        assert "rectangle" not in d


# ---------------------------------------------------------------------------
# MappingMatch tests
# ---------------------------------------------------------------------------

class TestMappingMatch:
    """Tests for MappingMatch data structure."""

    def test_default_status(self):
        m = MappingMatch(element_name="test")
        assert m.status == "NOT_FOUND"

    def test_found_match_to_dict(self):
        m = MappingMatch(
            element_name="ok_button",
            expected_name="OK",
            expected_control_type="Button",
            status="FOUND",
            matched_element={"name": "OK", "control_type": "Button"},
        )
        d = m.to_dict()
        assert d["element_name"] == "ok_button"
        assert d["status"] == "FOUND"
        assert d["matched_element"]["name"] == "OK"
        assert d["expected_name"] == "OK"

    def test_not_found_to_dict(self):
        m = MappingMatch(
            element_name="missing_element",
            expected_automation_id="txtMissing",
            status="NOT_FOUND",
        )
        d = m.to_dict()
        assert d["status"] == "NOT_FOUND"
        assert d["expected_automation_id"] == "txtMissing"
        assert "matched_element" not in d

    def test_error_to_dict(self):
        m = MappingMatch(
            element_name="broken",
            status="ERROR",
            error="Something went wrong",
        )
        d = m.to_dict()
        assert d["status"] == "ERROR"
        assert d["error"] == "Something went wrong"

    def test_optional_fields_omitted(self):
        m = MappingMatch(element_name="minimal")
        d = m.to_dict()
        assert "expected_name" not in d
        assert "expected_automation_id" not in d
        assert "matched_element" not in d
        assert "error" not in d


# ---------------------------------------------------------------------------
# DiscoveryReport tests
# ---------------------------------------------------------------------------

class TestDiscoveryReport:
    """Tests for DiscoveryReport data structure."""

    def test_to_dict_structure(self):
        r = DiscoveryReport(
            timestamp="2026-01-27T12:00:00",
            mozaik_window_title="Mozaik v2024",
            mozaik_process_id=1234,
            total_elements=50,
        )
        d = r.to_dict()
        assert d["timestamp"] == "2026-01-27T12:00:00"
        assert d["mozaik_window_title"] == "Mozaik v2024"
        assert d["mozaik_process_id"] == 1234
        assert d["total_elements"] == 50
        assert isinstance(d["elements"], list)
        assert isinstance(d["mapping_results"], list)
        assert isinstance(d["summary"], dict)


# ---------------------------------------------------------------------------
# compare_mapping tests
# ---------------------------------------------------------------------------

class TestCompareMapping:
    """Tests for comparing discovered elements against ElementMapping."""

    def test_finds_matching_by_name_and_control_type(self, sample_elements):
        mapping = {
            "file_menu": {"name": "File", "control_type": "MenuItem"},
        }
        results = compare_mapping(sample_elements, mapping)
        assert len(results) == 1
        assert results[0].status == "FOUND"
        assert results[0].matched_element["name"] == "File"

    def test_finds_matching_by_automation_id(self, sample_elements):
        mapping = {
            "design_canvas": {"automation_id": "designCanvas"},
        }
        results = compare_mapping(sample_elements, mapping)
        assert len(results) == 1
        assert results[0].status == "FOUND"
        assert results[0].matched_element["automation_id"] == "designCanvas"

    def test_not_found_when_missing(self, sample_elements):
        mapping = {
            "nonexistent": {"automation_id": "doesNotExist"},
        }
        results = compare_mapping(sample_elements, mapping)
        assert len(results) == 1
        assert results[0].status == "NOT_FOUND"

    def test_empty_elements_all_not_found(self, empty_elements):
        mapping = {
            "file_menu": {"name": "File", "control_type": "MenuItem"},
        }
        results = compare_mapping(empty_elements, mapping)
        assert results[0].status == "NOT_FOUND"

    def test_multiple_mappings(self, sample_elements):
        mapping = {
            "file_menu": {"name": "File", "control_type": "MenuItem"},
            "ok_button": {"name": "OK", "control_type": "Button"},
            "missing": {"automation_id": "nope"},
        }
        results = compare_mapping(sample_elements, mapping)
        statuses = {r.element_name: r.status for r in results}
        assert statuses["file_menu"] == "FOUND"
        assert statuses["ok_button"] == "FOUND"
        assert statuses["missing"] == "NOT_FOUND"

    def test_title_matching(self, sample_elements):
        """Title matches against element name (how dialogs appear in UIA)."""
        elements = [
            UIElement(name="Room Properties", control_type="Window", depth=0),
        ]
        mapping = {"room_dialog": {"title": "Room Properties"}}
        results = compare_mapping(elements, mapping)
        assert results[0].status == "FOUND"

    def test_automation_id_with_control_type_mismatch(self):
        """automation_id match but control_type mismatch should not match."""
        elements = [
            UIElement(automation_id="txtWidth", control_type="Edit", depth=0),
        ]
        mapping = {
            "width_input": {"automation_id": "txtWidth", "control_type": "Button"},
        }
        results = compare_mapping(elements, mapping)
        assert results[0].status == "NOT_FOUND"

    def test_automation_id_without_control_type_matches(self):
        """automation_id alone should match regardless of control_type."""
        elements = [
            UIElement(automation_id="txtWidth", control_type="Edit", depth=0),
        ]
        mapping = {
            "width_input": {"automation_id": "txtWidth"},
        }
        results = compare_mapping(elements, mapping)
        assert results[0].status == "FOUND"

    def test_default_mapping_has_expected_keys(self):
        """Verify DEFAULT_ELEMENT_MAPPING has all the expected entries."""
        expected_keys = {
            "file_menu", "file_new", "libraries_menu",
            "menu_bar", "layout_tab_control", "room_combo",
            "room_name_input", "design_canvas",
            "draw_walls_button", "quick_room_checkbox",
            "height_walls", "height_base_cabs", "height_wall_cabs",
            "depth_base_cabs", "depth_wall_cabs", "depth_tall_cabs",
            "save_button", "delete_button", "zoom_extents_button", "snap_button",
            "job_combo", "new_job_button",
            "door_library_combo", "base_handle_combo",
        }
        assert set(DEFAULT_ELEMENT_MAPPING.keys()) == expected_keys


# ---------------------------------------------------------------------------
# _find_matching_element tests
# ---------------------------------------------------------------------------

class TestFindMatchingElement:
    """Tests for _find_matching_element helper."""

    def test_match_by_automation_id(self):
        elements = [
            UIElement(automation_id="txtName", control_type="Edit"),
        ]
        result = _find_matching_element(elements, {"automation_id": "txtName"})
        assert result is not None
        assert result.automation_id == "txtName"

    def test_no_match_returns_none(self):
        elements = [UIElement(name="Other")]
        result = _find_matching_element(elements, {"automation_id": "missing"})
        assert result is None

    def test_name_only_without_control_type_no_match(self):
        """Name alone (without control_type) should not match."""
        elements = [UIElement(name="File", control_type="MenuItem")]
        result = _find_matching_element(elements, {"name": "File"})
        # name without control_type: our logic requires both for name matching
        assert result is None

    def test_title_match(self):
        elements = [UIElement(name="Cabinet Library", control_type="Window")]
        result = _find_matching_element(elements, {"title": "Cabinet Library"})
        assert result is not None


# ---------------------------------------------------------------------------
# build_report tests
# ---------------------------------------------------------------------------

class TestBuildReport:
    """Tests for building the final discovery report."""

    def test_basic_report(self, sample_elements):
        mapping_results = [
            MappingMatch(element_name="file_menu", status="FOUND"),
            MappingMatch(element_name="missing", status="NOT_FOUND"),
        ]
        report = build_report(
            window_title="Mozaik v2024",
            process_id=1234,
            window_rect={"left": 0, "top": 0, "right": 1920, "bottom": 1080},
            elements=sample_elements,
            mapping_results=mapping_results,
        )
        assert report.mozaik_window_title == "Mozaik v2024"
        assert report.mozaik_process_id == 1234
        assert report.total_elements == len(sample_elements)
        assert report.summary["mapping_found"] == 1
        assert report.summary["mapping_not_found"] == 1

    def test_empty_report(self):
        report = build_report(
            window_title="Empty",
            process_id=0,
            window_rect=None,
            elements=[],
            mapping_results=[],
        )
        assert report.total_elements == 0
        assert report.max_depth_reached == 0
        assert report.summary["mapping_found"] == 0

    def test_control_type_counts(self, sample_elements):
        report = build_report(
            window_title="Test",
            process_id=0,
            window_rect=None,
            elements=sample_elements,
            mapping_results=[],
        )
        counts = report.summary["control_type_counts"]
        assert counts["Button"] == 5  # Wall, Opening, Cabinet, OK, Cancel
        assert counts["MenuItem"] == 2  # File, New Room
        assert counts["Custom"] == 1  # designCanvas

    def test_report_serializable(self, sample_elements):
        mapping_results = [MappingMatch(element_name="test", status="FOUND")]
        report = build_report("Test", 0, None, sample_elements, mapping_results)
        # Must be JSON serializable
        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)
        assert parsed["mozaik_window_title"] == "Test"
        assert len(parsed["elements"]) == len(sample_elements)

    def test_max_depth_tracked(self):
        elements = [
            UIElement(depth=0),
            UIElement(depth=1),
            UIElement(depth=3),
            UIElement(depth=2),
        ]
        report = build_report("Test", 0, None, elements, [])
        assert report.max_depth_reached == 3

    def test_error_count_in_summary(self):
        mapping_results = [
            MappingMatch(element_name="a", status="FOUND"),
            MappingMatch(element_name="b", status="ERROR"),
            MappingMatch(element_name="c", status="NOT_FOUND"),
            MappingMatch(element_name="d", status="ERROR"),
        ]
        report = build_report("Test", 0, None, [], mapping_results)
        assert report.summary["mapping_found"] == 1
        assert report.summary["mapping_not_found"] == 1
        assert report.summary["mapping_errors"] == 2


# ---------------------------------------------------------------------------
# enumerate_elements tests (mocked pywinauto wrappers)
# ---------------------------------------------------------------------------

class TestEnumerateElements:
    """Tests for UI element enumeration with mocked pywinauto."""

    def _make_mock_wrapper(
        self,
        name: str = "",
        automation_id: str = "",
        control_type: str = "",
        class_name: str = "",
        children: list | None = None,
        enabled: bool = True,
        visible: bool = True,
    ) -> MagicMock:
        """Create a mock pywinauto wrapper element."""
        wrapper = MagicMock()
        info = MagicMock()
        info.name = name
        info.automation_id = automation_id
        info.control_type = control_type
        info.class_name = class_name
        info.enabled = enabled
        info.visible = visible

        rect = MagicMock()
        rect.left = 0
        rect.top = 0
        rect.right = 100
        rect.bottom = 50
        info.rectangle = rect

        wrapper.element_info = info
        wrapper.children.return_value = children or []
        return wrapper

    def test_enumerate_empty(self):
        parent = self._make_mock_wrapper(children=[])
        elements = enumerate_elements(parent, max_depth=5)
        assert len(elements) == 0

    def test_enumerate_flat_children(self):
        child1 = self._make_mock_wrapper(name="File", control_type="MenuItem")
        child2 = self._make_mock_wrapper(name="Edit", control_type="MenuItem")
        parent = self._make_mock_wrapper(children=[child1, child2])

        elements = enumerate_elements(parent, max_depth=5)
        assert len(elements) == 2
        assert elements[0].name == "File"
        assert elements[1].name == "Edit"

    def test_enumerate_nested(self):
        grandchild = self._make_mock_wrapper(name="New Room", control_type="MenuItem")
        child = self._make_mock_wrapper(name="File", control_type="MenuItem", children=[grandchild])
        parent = self._make_mock_wrapper(children=[child])

        elements = enumerate_elements(parent, max_depth=5)
        assert len(elements) == 2
        names = [e.name for e in elements]
        assert "File" in names
        assert "New Room" in names

    def test_depth_limit(self):
        grandchild = self._make_mock_wrapper(name="Deep", control_type="Button")
        child = self._make_mock_wrapper(name="Mid", control_type="Pane", children=[grandchild])
        parent = self._make_mock_wrapper(children=[child])

        # max_depth=0 should not recurse at all
        elements = enumerate_elements(parent, max_depth=0)
        assert len(elements) == 1  # Only "Mid", no recursion into grandchild
        assert elements[0].name == "Mid"

    def test_depth_limit_excludes_deep(self):
        deep = self._make_mock_wrapper(name="TooDeep")
        mid = self._make_mock_wrapper(name="Mid", children=[deep])
        top = self._make_mock_wrapper(name="Top", children=[mid])
        parent = self._make_mock_wrapper(children=[top])

        elements = enumerate_elements(parent, max_depth=1)
        names = [e.name for e in elements]
        assert "Top" in names
        assert "Mid" in names
        assert "TooDeep" not in names

    def test_children_count_set(self):
        child1 = self._make_mock_wrapper(name="A")
        child2 = self._make_mock_wrapper(name="B")
        parent_child = self._make_mock_wrapper(name="Parent", children=[child1, child2])
        root = self._make_mock_wrapper(children=[parent_child])

        elements = enumerate_elements(root, max_depth=5)
        # parent_child should have children_count=2
        parent_elem = next(e for e in elements if e.name == "Parent")
        assert parent_elem.children_count == 2

    def test_exception_in_children_handled(self):
        """If wrapper.children() raises, should gracefully return empty."""
        parent = MagicMock()
        parent.children.side_effect = Exception("Access denied")

        elements = enumerate_elements(parent, max_depth=5)
        assert len(elements) == 0


# ---------------------------------------------------------------------------
# _extract_element_info tests
# ---------------------------------------------------------------------------

class TestExtractElementInfo:
    """Tests for extracting element info from pywinauto wrapper."""

    def test_extracts_all_fields(self):
        wrapper = MagicMock()
        info = MagicMock()
        info.name = "OK"
        info.automation_id = "btnOK"
        info.control_type = "Button"
        info.class_name = "ButtonCtrl"
        info.enabled = True
        info.visible = True
        rect = MagicMock()
        rect.left = 10
        rect.top = 20
        rect.right = 110
        rect.bottom = 60
        info.rectangle = rect
        wrapper.element_info = info

        elem = _extract_element_info(wrapper, depth=2)
        assert elem is not None
        assert elem.name == "OK"
        assert elem.automation_id == "btnOK"
        assert elem.control_type == "Button"
        assert elem.depth == 2
        assert elem.rectangle == {"left": 10, "top": 20, "right": 110, "bottom": 60}

    def test_handles_missing_rectangle(self):
        wrapper = MagicMock()
        info = MagicMock(spec=[])  # spec=[] prevents auto-creating attributes
        info.name = "NoRect"
        info.automation_id = ""
        info.control_type = "Pane"
        info.class_name = ""
        info.enabled = True
        info.visible = True
        # Make rectangle access raise an AttributeError
        type(info).rectangle = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no rect"))
        )
        wrapper.element_info = info

        elem = _extract_element_info(wrapper, depth=0)
        assert elem is not None
        assert elem.rectangle is None

    def test_returns_none_on_total_failure(self):
        wrapper = MagicMock()
        wrapper.element_info = property(lambda s: (_ for _ in ()).throw(Exception("fail")))
        type(wrapper).element_info = property(lambda s: (_ for _ in ()).throw(Exception("fail")))

        elem = _extract_element_info(wrapper, depth=0)
        assert elem is None
