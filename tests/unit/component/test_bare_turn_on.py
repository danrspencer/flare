"""What counts as a bare turn-on, which runs a flare's automation."""

import pytest

from custom_components.flare.flares.bare import is_bare_turn_on


@pytest.mark.parametrize("kwargs", [{}, {"transition": 2}])
def test_nothing_but_on_is_bare(kwargs):
    assert is_bare_turn_on(kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [{"brightness": 10}, {"color_temp_kelvin": 3000}, {"rgb_color": (1, 2, 3)}, {"effect": "x"}, {"brightness": 10, "transition": 2}],
)
def test_any_value_is_not_bare(kwargs):
    assert not is_bare_turn_on(kwargs)
