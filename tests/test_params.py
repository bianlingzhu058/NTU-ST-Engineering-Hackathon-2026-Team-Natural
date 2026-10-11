"""The parameters table is the single source of behaviour numbers, each with a source and a tag."""
import pytest
from agent.behaviour import params


def test_every_parameter_has_a_source_and_a_known_confidence():
    for name, value, source, confidence in params.table():
        assert source.strip(), name
        assert confidence in {"H", "M", "L", "D", "U"}, name


def test_overrides_apply_and_unknown_names_fail():
    try:
        params.configure({"scroll.notch_px": 120.0})
        assert params.P("scroll.notch_px") == 120.0
        with pytest.raises(KeyError):
            params.configure({"scroll.notch_pixels": 1})
    finally:
        params.configure({})
