"""The Zones entry's options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TICK_GAP,
    CONF_TICK_INTERVAL,
    CONF_TWO_STEP_MODELS,
    DEFAULT_MIN_BRIGHTNESS_CHANGE,
    DEFAULT_MIN_COLOR_TEMP_CHANGE,
    DEFAULT_TICK_GAP,
    DEFAULT_TICK_INTERVAL,
)
from .services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS


class FlareOptionsFlow(config_entries.OptionsFlow):
    """The Zones entry's options: which bulb models need two-step transitions
    (see two_step.py), the zones' tick timing, and the smallest change worth
    sending. The models field is pre-filled with the shipped defaults and is
    the whole list."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        fields: dict = {
            vol.Optional(CONF_TWO_STEP_MODELS, default=""): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
        suggested: dict = {
            CONF_TWO_STEP_MODELS: options.get(CONF_TWO_STEP_MODELS) or "\n".join(DEFAULT_TWO_STEP_MODEL_PATTERNS),
        }
        for key, default, minimum, maximum, step, unit in (
            (CONF_TICK_INTERVAL, DEFAULT_TICK_INTERVAL, 1, 60, 1, "min"),
            (CONF_TICK_GAP, DEFAULT_TICK_GAP, 0, 10, 0.5, "s"),
            (CONF_MIN_BRIGHTNESS_CHANGE, DEFAULT_MIN_BRIGHTNESS_CHANGE, 0, 25, 0.5, "%"),
            (CONF_MIN_COLOR_TEMP_CHANGE, DEFAULT_MIN_COLOR_TEMP_CHANGE, 0, 50, 0.5, "mired"),
        ):
            fields[vol.Required(key, default=options.get(key, default))] = _number(minimum, maximum, step, unit)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested),
        )


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )
