"""Tests for the pure helpers (polarity, icons, per-output settings)."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "pal_es"

pkg = types.ModuleType("pal_es_logic_test")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["pal_es_logic_test"] = pkg
logic = importlib.import_module("pal_es_logic_test.logic")
const = importlib.import_module("pal_es_logic_test.const")


def test_gate_state_default_polarity():
    assert logic.gate_state("active", False) == "closed"
    assert logic.gate_state("idle", False) == "open"


def test_gate_state_inverted():
    assert logic.gate_state("active", True) == "open"
    assert logic.gate_state("idle", True) == "closed"


def test_gate_state_unknown_values():
    assert logic.gate_state(None, False) == "unknown"
    assert logic.gate_state("weird", True) == "unknown"


def test_icons_differ_for_open_and_closed():
    for icon_type in const.ICONS:
        assert logic.gate_icon(icon_type, "open") != logic.gate_icon(icon_type, "closed")
    assert logic.gate_icon("barrier", "unknown") == logic.gate_icon("barrier", "closed")
    assert logic.gate_icon("nonsense", "open") == logic.gate_icon(const.DEFAULT_ICON_TYPE, "open")


def test_settings_per_output_and_defaults():
    options = {
        "outputs": {
            "DEV1:1": {"icon_type": "barrier", "invert": True},
            "DEV1:2": {"icon_type": "garage_door", "invert": False},
        }
    }
    assert logic.output_settings(options, "DEV1", 1) == {"icon_type": "barrier", "invert": True}
    assert logic.output_settings(options, "DEV1", 2) == {"icon_type": "garage_door", "invert": False}
    # unknown output -> defaults
    assert logic.output_settings(options, "DEV9", 1) == {
        "icon_type": const.DEFAULT_ICON_TYPE,
        "invert": False,
    }


def test_legacy_global_invert_is_default():
    assert logic.output_settings({"invert_input": True}, "DEV1", 1)["invert"] is True
    # explicit per-output value wins over the legacy global one
    options = {"invert_input": True, "outputs": {"DEV1:1": {"invert": False}}}
    assert logic.output_settings(options, "DEV1", 1)["invert"] is False
