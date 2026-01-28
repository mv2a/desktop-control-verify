"""
Tests for overnight_discovery.py pure logic.

Tests report building, checkpoint save/load, element extraction,
phase timeout, deduplication, and dialog close ordering without
requiring pywinauto or a running Mozaik instance.
"""

import json
import sys
import time
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import from scripts directory
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from overnight_discovery import (
    DIALOG_CLOSE_BUTTONS,
    LAYOUT_TABS,
    PHASE_BUDGETS_SECONDS,
    PHASE_FUNCTIONS,
    PHASE_NAMES,
    DiscoveredElement,
    OvernightReport,
    PhaseRunner,
    build_element_key,
    extract_element,
    get_dialog_close_order,
    load_checkpoint,
    merge_elements,
    save_checkpoint,
    _count_control_types,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_element() -> DiscoveredElement:
    return DiscoveredElement(
        automation_id="RoomNameTextBox",
        name="Room Name",
        control_type="Edit",
        class_name="TextBoxControl",
        tab="Room",
        subtab="",
        enabled=True,
        visible=True,
        depth=2,
    )


@pytest.fixture
def sample_elements() -> list:
    return [
        DiscoveredElement(
            automation_id="RoomNameTextBox",
            name="Room Name",
            control_type="Edit",
            tab="Room",
            depth=1,
        ),
        DiscoveredElement(
            automation_id="SchematicCanvas",
            name="",
            control_type="Custom",
            tab="Room",
            depth=1,
            rectangle={"left": 0, "top": 0, "right": 744, "bottom": 592},
        ),
        DiscoveredElement(
            automation_id="H_WallsTextBox",
            name="Wall Height",
            control_type="Edit",
            tab="Room",
            subtab="Heights",
            depth=3,
            current_value="96",
        ),
        DiscoveredElement(
            automation_id="DoorLibSelComboBox",
            name="Door Library",
            control_type="ComboBox",
            tab="Settings",
            depth=2,
            combo_options=["Shaker", "Flat", "Raised"],
        ),
        DiscoveredElement(
            automation_id="",
            name="File",
            control_type="MenuItem",
            tab="",
            depth=0,
        ),
    ]


@pytest.fixture
def empty_report() -> OvernightReport:
    return OvernightReport()


@pytest.fixture
def logger():
    lg = logging.getLogger("test_overnight")
    lg.setLevel(logging.DEBUG)
    return lg


# ---------------------------------------------------------------------------
# DiscoveredElement tests
# ---------------------------------------------------------------------------

class TestDiscoveredElement:
    def test_default_values(self):
        elem = DiscoveredElement()
        assert elem.automation_id == ""
        assert elem.name == ""
        assert elem.control_type == ""
        assert elem.class_name == ""
        assert elem.rectangle is None
        assert elem.enabled is True
        assert elem.visible is True
        assert elem.tab == ""
        assert elem.subtab == ""
        assert elem.parent_id == ""
        assert elem.depth == 0
        assert elem.current_value is None
        assert elem.combo_options is None
        assert elem.access_key is None

    def test_to_dict_basic(self, sample_element):
        d = sample_element.to_dict()
        assert d["automation_id"] == "RoomNameTextBox"
        assert d["name"] == "Room Name"
        assert d["control_type"] == "Edit"
        assert d["tab"] == "Room"
        assert d["enabled"] is True
        assert d["visible"] is True
        assert d["depth"] == 2

    def test_to_dict_with_rectangle(self):
        elem = DiscoveredElement(
            automation_id="Canvas",
            rectangle={"left": 10, "top": 20, "right": 100, "bottom": 200},
        )
        d = elem.to_dict()
        assert d["rectangle"] == {"left": 10, "top": 20, "right": 100, "bottom": 200}

    def test_to_dict_without_rectangle(self):
        elem = DiscoveredElement(automation_id="NoRect")
        d = elem.to_dict()
        assert "rectangle" not in d

    def test_to_dict_with_current_value(self):
        elem = DiscoveredElement(
            automation_id="TextBox1",
            control_type="Edit",
            current_value="hello",
        )
        d = elem.to_dict()
        assert d["current_value"] == "hello"

    def test_to_dict_without_current_value(self):
        elem = DiscoveredElement(automation_id="TextBox1")
        d = elem.to_dict()
        assert "current_value" not in d

    def test_to_dict_with_combo_options(self):
        elem = DiscoveredElement(
            automation_id="Combo1",
            control_type="ComboBox",
            combo_options=["A", "B", "C"],
        )
        d = elem.to_dict()
        assert d["combo_options"] == ["A", "B", "C"]

    def test_to_dict_with_access_key(self):
        elem = DiscoveredElement(
            automation_id="Btn1",
            access_key="Alt+F",
        )
        d = elem.to_dict()
        assert d["access_key"] == "Alt+F"

    def test_to_dict_with_parent_id(self):
        elem = DiscoveredElement(
            automation_id="Child1",
            parent_id="Parent1",
        )
        d = elem.to_dict()
        assert d["parent_id"] == "Parent1"

    def test_to_dict_omits_empty_parent_id(self):
        elem = DiscoveredElement(automation_id="Child1", parent_id="")
        d = elem.to_dict()
        assert "parent_id" not in d

    def test_to_dict_json_serializable(self, sample_element):
        d = sample_element.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["automation_id"] == "RoomNameTextBox"


# ---------------------------------------------------------------------------
# build_element_key tests
# ---------------------------------------------------------------------------

class TestBuildElementKey:
    def test_key_from_automation_id(self):
        elem = DiscoveredElement(automation_id="RoomNameTextBox")
        assert build_element_key(elem) == "RoomNameTextBox"

    def test_key_from_automation_id_ignores_name(self):
        elem = DiscoveredElement(
            automation_id="MyId", name="MyName", control_type="Button"
        )
        assert build_element_key(elem) == "MyId"

    def test_key_fallback_to_name_type(self):
        elem = DiscoveredElement(
            automation_id="", name="File", control_type="MenuItem"
        )
        assert build_element_key(elem) == "File|MenuItem"

    def test_key_with_tab(self):
        elem = DiscoveredElement(
            automation_id="", name="OK", control_type="Button", tab="Room"
        )
        assert build_element_key(elem) == "OK|Button|Room"

    def test_key_with_tab_and_subtab(self):
        elem = DiscoveredElement(
            automation_id="", name="Value",
            control_type="Edit", tab="Room", subtab="Heights",
        )
        assert build_element_key(elem) == "Value|Edit|Room|Heights"

    def test_key_unnamed(self):
        elem = DiscoveredElement(automation_id="", name="", control_type="Pane")
        assert build_element_key(elem) == "(unnamed)|Pane"

    def test_key_no_info(self):
        elem = DiscoveredElement()
        assert build_element_key(elem) == "(unnamed)|(unknown)"


# ---------------------------------------------------------------------------
# OvernightReport tests
# ---------------------------------------------------------------------------

class TestOvernightReport:
    def test_default_report(self, empty_report):
        assert empty_report.metadata == {}
        assert empty_report.elements == {}
        assert empty_report.tabs == {}
        assert empty_report.dialogs == {}
        assert empty_report.menus == {}
        assert empty_report.combobox_values == {}
        assert empty_report.context_menus == {}
        assert empty_report.errors == []
        assert empty_report.timing == {}

    def test_to_dict(self, empty_report):
        empty_report.metadata = {"start_time": "2026-01-27T22:00:00"}
        d = empty_report.to_dict()
        assert d["metadata"]["start_time"] == "2026-01-27T22:00:00"
        assert isinstance(d["elements"], dict)
        assert isinstance(d["errors"], list)

    def test_to_dict_json_serializable(self, empty_report):
        empty_report.metadata = {"test": True}
        empty_report.elements = {"A": {"name": "A"}}
        json_str = json.dumps(empty_report.to_dict())
        parsed = json.loads(json_str)
        assert parsed["metadata"]["test"] is True
        assert parsed["elements"]["A"]["name"] == "A"

    def test_merge_checkpoint_elements(self, empty_report):
        empty_report.elements = {"A": {"name": "A"}}
        checkpoint = {"elements": {"B": {"name": "B"}, "C": {"name": "C"}}}
        empty_report.merge_checkpoint(checkpoint)
        assert "A" in empty_report.elements
        assert "B" in empty_report.elements
        assert "C" in empty_report.elements

    def test_merge_checkpoint_overwrites(self, empty_report):
        empty_report.elements = {"A": {"name": "old"}}
        checkpoint = {"elements": {"A": {"name": "new"}}}
        empty_report.merge_checkpoint(checkpoint)
        assert empty_report.elements["A"]["name"] == "new"

    def test_merge_checkpoint_errors(self, empty_report):
        empty_report.errors = [{"error": "first"}]
        checkpoint = {"errors": [{"error": "second"}]}
        empty_report.merge_checkpoint(checkpoint)
        assert len(empty_report.errors) == 2
        assert empty_report.errors[1]["error"] == "second"

    def test_merge_checkpoint_timing(self, empty_report):
        empty_report.timing = {"phase_a": 1.0}
        checkpoint = {"timing": {"phase_b": 2.5}}
        empty_report.merge_checkpoint(checkpoint)
        assert empty_report.timing["phase_a"] == 1.0
        assert empty_report.timing["phase_b"] == 2.5

    def test_merge_checkpoint_combobox(self, empty_report):
        checkpoint = {"combobox_values": {"Combo1": ["A", "B"]}}
        empty_report.merge_checkpoint(checkpoint)
        assert empty_report.combobox_values["Combo1"] == ["A", "B"]

    def test_merge_checkpoint_dialogs(self, empty_report):
        checkpoint = {
            "dialogs": {"Products": {"element_count": 42}},
        }
        empty_report.merge_checkpoint(checkpoint)
        assert empty_report.dialogs["Products"]["element_count"] == 42

    def test_merge_checkpoint_menus(self, empty_report):
        checkpoint = {"menus": {"File": {"items": [{"name": "New"}]}}}
        empty_report.merge_checkpoint(checkpoint)
        assert empty_report.menus["File"]["items"][0]["name"] == "New"

    def test_merge_checkpoint_empty(self, empty_report):
        empty_report.merge_checkpoint({})
        assert empty_report.elements == {}
        assert empty_report.errors == []

    def test_merge_checkpoint_context_menus(self, empty_report):
        checkpoint = {
            "context_menus": {"canvas": {"items": [{"name": "Zoom"}]}},
        }
        empty_report.merge_checkpoint(checkpoint)
        assert empty_report.context_menus["canvas"]["items"][0]["name"] == "Zoom"


# ---------------------------------------------------------------------------
# merge_elements tests
# ---------------------------------------------------------------------------

class TestMergeElements:
    def test_merge_into_empty(self, sample_elements):
        result = merge_elements({}, sample_elements)
        assert "RoomNameTextBox" in result
        assert "SchematicCanvas" in result

    def test_merge_deduplicates(self):
        elem1 = DiscoveredElement(automation_id="A", name="Elem", tab="Room")
        elem2 = DiscoveredElement(automation_id="A", name="Elem Updated", tab="Room")
        result = merge_elements({}, [elem1, elem2])
        assert len(result) == 1
        assert result["A"]["name"] == "Elem Updated"

    def test_merge_preserves_existing(self):
        existing = {"A": {"name": "Existing"}}
        new_elem = DiscoveredElement(automation_id="B", name="New", tab="Room")
        result = merge_elements(existing, [new_elem])
        assert "A" in result
        assert "B" in result

    def test_merge_tab_element_overwrites_no_tab(self):
        existing = {"A": {"name": "NoTab", "tab": ""}}
        new_elem = DiscoveredElement(automation_id="A", name="WithTab", tab="Room")
        result = merge_elements(existing, [new_elem])
        assert result["A"]["name"] == "WithTab"

    def test_merge_empty_elements(self):
        result = merge_elements({}, [])
        assert result == {}

    def test_merge_nameless_elements(self):
        elem = DiscoveredElement(
            automation_id="", name="", control_type="Pane", tab="Room"
        )
        result = merge_elements({}, [elem])
        assert len(result) == 1
        key = list(result.keys())[0]
        assert "(unnamed)" in key


# ---------------------------------------------------------------------------
# Checkpoint save/load tests
# ---------------------------------------------------------------------------

class TestCheckpoints:
    def test_save_checkpoint(self, tmp_path):
        data = {"phase": 1, "elements": {"A": {"name": "A"}}}
        filepath = save_checkpoint(data, tmp_path, "baseline")
        assert Path(filepath).exists()
        assert "checkpoint_after_baseline_" in filepath
        assert filepath.endswith(".json")

    def test_load_checkpoint(self, tmp_path):
        data = {"phase": 2, "result": "ok"}
        filepath = save_checkpoint(data, tmp_path, "test")
        loaded = load_checkpoint(filepath)
        assert loaded["phase"] == 2
        assert loaded["result"] == "ok"

    def test_checkpoint_creates_directory(self, tmp_path):
        data = {"test": True}
        out = tmp_path / "subdir"
        filepath = save_checkpoint(data, out, "test")
        assert Path(filepath).exists()
        assert (out / "checkpoints").is_dir()

    def test_checkpoint_json_format(self, tmp_path):
        data = {
            "elements": {"X": {"name": "X", "rect": [1, 2, 3, 4]}},
            "errors": [{"msg": "test error"}],
        }
        filepath = save_checkpoint(data, tmp_path, "format")
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded["elements"]["X"]["name"] == "X"
        assert loaded["errors"][0]["msg"] == "test error"


# ---------------------------------------------------------------------------
# extract_element tests (mocked pywinauto wrapper)
# ---------------------------------------------------------------------------

class TestExtractElement:
    def _make_mock_wrapper(
        self,
        name: str = "",
        automation_id: str = "",
        control_type: str = "",
        class_name: str = "",
        enabled: bool = True,
        visible: bool = True,
        access_key: str = "",
    ) -> MagicMock:
        wrapper = MagicMock()
        info = MagicMock()
        info.name = name
        info.automation_id = automation_id
        info.control_type = control_type
        info.class_name = class_name
        info.enabled = enabled
        info.visible = visible
        info.access_key = access_key or None

        rect = MagicMock()
        rect.left = 0
        rect.top = 0
        rect.right = 100
        rect.bottom = 50
        info.rectangle = rect

        wrapper.element_info = info
        return wrapper

    def test_extract_basic(self):
        w = self._make_mock_wrapper(
            name="OK", automation_id="btnOK", control_type="Button"
        )
        elem = extract_element(w, depth=2, tab="Room")
        assert elem is not None
        assert elem.automation_id == "btnOK"
        assert elem.name == "OK"
        assert elem.control_type == "Button"
        assert elem.depth == 2
        assert elem.tab == "Room"

    def test_extract_with_rectangle(self):
        w = self._make_mock_wrapper(automation_id="Canvas")
        elem = extract_element(w)
        assert elem is not None
        assert elem.rectangle is not None
        assert elem.rectangle["left"] == 0
        assert elem.rectangle["right"] == 100

    def test_extract_with_access_key(self):
        w = self._make_mock_wrapper(
            name="File", control_type="MenuItem", access_key="Alt+F"
        )
        elem = extract_element(w)
        assert elem is not None
        assert elem.access_key == "Alt+F"

    def test_extract_tab_and_subtab(self):
        w = self._make_mock_wrapper(automation_id="H_WallsTextBox")
        elem = extract_element(w, tab="Room", subtab="Heights")
        assert elem is not None
        assert elem.tab == "Room"
        assert elem.subtab == "Heights"

    def test_extract_parent_id(self):
        w = self._make_mock_wrapper(automation_id="Child")
        elem = extract_element(w, parent_id="Parent")
        assert elem is not None
        assert elem.parent_id == "Parent"

    def test_extract_returns_none_on_failure(self):
        w = MagicMock()
        type(w).element_info = property(
            lambda s: (_ for _ in ()).throw(Exception("fail"))
        )
        elem = extract_element(w)
        assert elem is None

    def test_extract_missing_rectangle(self):
        w = MagicMock()

        class FakeInfo:
            name = "NoRect"
            automation_id = ""
            control_type = "Pane"
            class_name = ""
            enabled = True
            visible = True
            access_key = None

            @property
            def rectangle(self):
                raise AttributeError("no rect")

        w.element_info = FakeInfo()
        elem = extract_element(w)
        assert elem is not None
        assert elem.rectangle is None

    def test_extract_disabled_element(self):
        w = self._make_mock_wrapper(
            automation_id="Btn1", enabled=False, visible=True
        )
        elem = extract_element(w)
        assert elem is not None
        assert elem.enabled is False
        assert elem.visible is True


# ---------------------------------------------------------------------------
# PhaseRunner tests
# ---------------------------------------------------------------------------

class TestPhaseRunner:
    def test_successful_phase(self, logger):
        runner = PhaseRunner(0, "test", budget_s=10, logger=logger)

        def good_func():
            return {"result": "ok"}

        result = runner.run(good_func)
        assert result == {"result": "ok"}
        assert runner.error is None
        assert runner.elapsed > 0

    def test_phase_with_error(self, logger):
        runner = PhaseRunner(1, "error_test", budget_s=10, logger=logger)

        def bad_func():
            raise ValueError("test error")

        result = runner.run(bad_func)
        assert result is None
        assert runner.error is not None
        assert "ValueError" in runner.error

    def test_phase_timeout(self, logger):
        runner = PhaseRunner(2, "timeout_test", budget_s=1, logger=logger)

        def slow_func():
            time.sleep(10)
            return {"never": "reached"}

        result = runner.run(slow_func)
        # Result may or may not be set (thread still running)
        assert runner.error is not None
        assert "timed out" in runner.error.lower() or "Timed out" in runner.error

    def test_phase_records_elapsed(self, logger):
        runner = PhaseRunner(3, "timing_test", budget_s=10, logger=logger)

        def quick_func():
            time.sleep(0.1)
            return {}

        runner.run(quick_func)
        assert runner.elapsed >= 0.05  # Should be ~0.1s

    def test_phase_passes_args(self, logger):
        runner = PhaseRunner(4, "args_test", budget_s=10, logger=logger)

        def func_with_args(a, b, c=None):
            return {"sum": a + b, "c": c}

        result = runner.run(func_with_args, 1, 2, c="hello")
        assert result == {"sum": 3, "c": "hello"}


# ---------------------------------------------------------------------------
# Dialog close order tests
# ---------------------------------------------------------------------------

class TestDialogCloseOrder:
    def test_close_order_returns_list(self):
        order = get_dialog_close_order()
        assert isinstance(order, list)
        assert len(order) > 0

    def test_cancel_is_first(self):
        order = get_dialog_close_order()
        assert order[0] == "Cancel"

    def test_close_is_in_list(self):
        order = get_dialog_close_order()
        assert "Close" in order

    def test_no_is_in_list(self):
        order = get_dialog_close_order()
        assert "No" in order

    def test_order_matches_constant(self):
        order = get_dialog_close_order()
        assert order == list(DIALOG_CLOSE_BUTTONS)


# ---------------------------------------------------------------------------
# Configuration constant tests
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_all_phases_have_budgets(self):
        for phase_num in PHASE_FUNCTIONS:
            assert phase_num in PHASE_BUDGETS_SECONDS, (
                f"Phase {phase_num} missing budget"
            )

    def test_all_phases_have_names(self):
        for phase_num in PHASE_FUNCTIONS:
            assert phase_num in PHASE_NAMES, (
                f"Phase {phase_num} missing name"
            )

    def test_phase_budgets_positive(self):
        for phase_num, budget in PHASE_BUDGETS_SECONDS.items():
            assert budget > 0, f"Phase {phase_num} has non-positive budget"

    def test_phase_names_unique(self):
        names = list(PHASE_NAMES.values())
        assert len(names) == len(set(names)), "Phase names not unique"

    def test_total_budget_reasonable(self):
        total = sum(PHASE_BUDGETS_SECONDS.values())
        # Should be roughly 9 hours = 32400s, allow 6-12 hours
        assert 6 * 3600 <= total <= 12 * 3600, (
            f"Total budget {total}s outside expected range"
        )

    def test_16_phases(self):
        assert len(PHASE_FUNCTIONS) == 16

    def test_layout_tabs(self):
        assert LAYOUT_TABS == ["Job", "Settings", "Room", "Order"]


# ---------------------------------------------------------------------------
# _count_control_types tests
# ---------------------------------------------------------------------------

class TestCountControlTypes:
    def test_count_basic(self, sample_elements):
        counts = _count_control_types(sample_elements)
        assert counts["Edit"] == 2  # RoomNameTextBox, H_WallsTextBox
        assert counts["Custom"] == 1  # SchematicCanvas
        assert counts["ComboBox"] == 1  # DoorLibSelComboBox
        assert counts["MenuItem"] == 1  # File

    def test_count_empty(self):
        counts = _count_control_types([])
        assert counts == {}

    def test_count_unknown(self):
        elems = [DiscoveredElement(control_type="")]
        counts = _count_control_types(elems)
        assert counts["(unknown)"] == 1

    def test_count_all_same(self):
        elems = [
            DiscoveredElement(control_type="Button"),
            DiscoveredElement(control_type="Button"),
            DiscoveredElement(control_type="Button"),
        ]
        counts = _count_control_types(elems)
        assert counts == {"Button": 3}


# ---------------------------------------------------------------------------
# Integration: report round-trip
# ---------------------------------------------------------------------------

class TestReportRoundTrip:
    def test_full_report_serializable(self, sample_elements):
        report = OvernightReport()
        report.metadata = {
            "start_time": "2026-01-27T22:00:00",
            "end_time": "2026-01-28T07:00:00",
            "window_title": "Mozaik Enterprise",
            "pid": 12345,
        }
        report.elements = merge_elements({}, sample_elements)
        report.combobox_values = {"Combo1": ["A", "B"]}
        report.menus = {"File": {"items": [{"name": "New"}]}}
        report.errors = [{"phase": 5, "error": "timeout"}]
        report.timing = {"phase_baseline": 39.2}

        # Serialize
        json_str = json.dumps(report.to_dict(), default=str)
        parsed = json.loads(json_str)

        # Verify structure
        assert parsed["metadata"]["pid"] == 12345
        assert "RoomNameTextBox" in parsed["elements"]
        assert parsed["combobox_values"]["Combo1"] == ["A", "B"]
        assert parsed["menus"]["File"]["items"][0]["name"] == "New"
        assert len(parsed["errors"]) == 1
        assert parsed["timing"]["phase_baseline"] == 39.2

    def test_checkpoint_round_trip(self, tmp_path, sample_elements):
        report = OvernightReport()
        merged = merge_elements({}, sample_elements)
        data = {
            "phase": 1,
            "elements": merged,
            "timing": {"phase_baseline": 42.0},
        }
        filepath = save_checkpoint(data, tmp_path, "baseline")
        loaded = load_checkpoint(filepath)
        assert loaded["phase"] == 1
        assert "RoomNameTextBox" in loaded["elements"]
        assert loaded["timing"]["phase_baseline"] == 42.0

    def test_merge_multiple_checkpoints(self, empty_report):
        ckpt1 = {
            "elements": {"A": {"name": "A"}},
            "timing": {"phase_a": 1.0},
            "errors": [{"error": "e1"}],
        }
        ckpt2 = {
            "elements": {"B": {"name": "B"}},
            "timing": {"phase_b": 2.0},
            "errors": [{"error": "e2"}],
        }
        empty_report.merge_checkpoint(ckpt1)
        empty_report.merge_checkpoint(ckpt2)
        assert "A" in empty_report.elements
        assert "B" in empty_report.elements
        assert empty_report.timing["phase_a"] == 1.0
        assert empty_report.timing["phase_b"] == 2.0
        assert len(empty_report.errors) == 2
