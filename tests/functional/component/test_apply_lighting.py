"""apply_lighting against real state: dispatch, override protection across
real claims, two-step transitions and force."""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.flare.const import (
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TWO_STEP_MODELS,
    DOMAIN,
)
from tests.functional.component.harness import (
    CT,
    add_device_light,
    apply_lighting,
    claim_registry,
    claims_check,
    label_two_step,
    zone_id,
    set_light,
    setup_zones_entry,
    zone_device_id,
)
from tests.support.claims import claim_field

TRADFRI = "TRADFRI bulb GU10, color/white spectrum, 345 lm"


async def test_turns_on_reachable_entities(setup_integration: HomeAssistant):
    hass = setup_integration
    turn_on = async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, transition=2)

    assert [c.data for c in turn_on] == [{"entity_id": ["light.a"], "brightness": 180, "color_temp_kelvin": 3200, "transition": 2}]


async def test_a_turn_off_records_an_off_target(setup_integration: HomeAssistant):
    """So our own off can still be told apart once its context expires."""
    hass = setup_integration
    turn_off = async_mock_service(hass, "light", "turn_off")
    async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    set_light(hass, "light.b", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)

    await apply_lighting(hass, ["light.a", "light.b"], brightness_levels={"light.a": 0})

    assert turn_off[-1].data["entity_id"] == ["light.a"]
    assert claim_registry(hass).all_records()["light.a"]["latest"]["target"] == {"state": "off"}


class TestOverrideProtection:
    async def test_a_light_changed_after_our_first_write_is_left_alone(self, setup_integration: HomeAssistant):
        """With only one write so far, `observed` is the pre-write baseline."""
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "off", supported_color_modes=CT)

        ours = Context()
        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=ours)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200, context=ours)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200)  # someone else

        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200)

        assert len(turn_on) == 1

    async def test_a_delayed_echo_under_a_new_context_does_not_lock_the_light_out(self, setup_integration: HomeAssistant):
        """HA forgets a write's context after 5s, so a slow device echoes our
        value under a new one. It must still follow the curve afterwards."""
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "off", supported_color_modes=CT)

        # Two landed writes, so `observed` is a real promoted claim.
        first, second = Context(), Context()
        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=first)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200, context=first)
        await apply_lighting(hass, ["light.a"], context=second)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, color_temp_kelvin=3000, context=second)

        # The echo: within tolerance, new context. (An identical value
        # wouldn't change state, so the context wouldn't change either.)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=201, color_temp_kelvin=3005)
        await apply_lighting(hass, ["light.a"])
        assert len(turn_on) == 2

        await apply_lighting(hass, ["light.a"], brightness=100, color_temp_kelvin=4500)
        assert len(turn_on) == 3

    async def test_a_dropped_first_write_is_retried(self, setup_integration: HomeAssistant):
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200)

        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200)
        # The bulb never adopts it: state untouched.
        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200)

        assert len(turn_on) == 2

    async def test_force_writes_through_and_the_write_is_then_ours(self, setup_integration: HomeAssistant):
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200)
        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200)

        forced = Context()
        await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, force=True, context=forced)
        assert len(turn_on) == 2

        # Landed under the forced context but short of target: ours, and
        # still needing a write. (95, not 90, so state actually changes.)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=95, color_temp_kelvin=3200, context=forced)
        result = await hass.services.async_call(
            DOMAIN,
            "compute_lighting_groups",
            {"entities": ["light.a"], "brightness": 180, "color_temp_kelvin": 3200, "zone_device_id": zone_device_id(hass)},
            blocking=True,
            return_response=True,
        )
        assert result["groups"][0]["combined"] == ["light.a"]


class TestTwoStep:
    async def test_brightness_then_colour_each_under_its_own_context(self, setup_integration: HomeAssistant):
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        await label_two_step(hass, "light.a")
        set_light(hass, "light.a", "off", supported_color_modes=CT)

        await apply_lighting(hass, ["light.a"], transition=0.2)

        brightness_call, color_call = turn_on
        assert brightness_call.data == {"entity_id": ["light.a"], "transition": 0.1, "brightness": 200}
        assert color_call.data["color_temp_kelvin"] == 3000
        assert brightness_call.context.id != color_call.context.id
        registry, zone = claim_registry(hass), zone_id(hass)
        assert claim_field(registry, zone, "light.a", "latest", "context_id") == color_call.context.id
        assert claim_field(registry, zone, "light.a", "latest", "secondary_context_id") == brightness_call.context.id

    async def test_the_brightness_step_landing_alone_is_ours(self, setup_integration: HomeAssistant):
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        await label_two_step(hass, "light.a")
        set_light(hass, "light.a", "off", supported_color_modes=CT)

        await apply_lighting(hass, ["light.a"], transition=0.2)
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, context=turn_on[0].context)

        assert (await claims_check(hass, ["light.a"]))["light.a"] == {
            "blocked": False,
            "status": "controlled",
            "matched_via": "latest-context",
            "zone": "Test Zone",
        }

    async def test_only_the_brightness_step_landing_still_promotes_the_write(self, setup_integration: HomeAssistant):
        """The colour step dropped; the write still counts as landed on the
        next call."""
        hass = setup_integration
        async_mock_service(hass, "light", "turn_on")
        await label_two_step(hass, "light.a")
        set_light(hass, "light.a", "off", supported_color_modes=CT)
        registry, zone = claim_registry(hass), zone_id(hass)

        await apply_lighting(hass, ["light.a"], transition=0.2)
        brightness_ctx = claim_field(registry, zone, "light.a", "latest", "secondary_context_id")
        color_ctx = claim_field(registry, zone, "light.a", "latest", "context_id")
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, context=Context(id=brightness_ctx))
        await apply_lighting(hass, ["light.a"], transition=0.2)

        assert claim_field(registry, zone, "light.a", "observed", "context_id") == color_ctx
        assert claim_field(registry, zone, "light.a", "observed", "secondary_context_id") == brightness_ctx

    async def test_a_device_matching_the_default_patterns_needs_no_label(self, hass: HomeAssistant):
        await setup_zones_entry(hass)
        turn_on = async_mock_service(hass, "light", "turn_on")
        await add_device_light(hass, "light.spot_1", manufacturer="IKEA", model=TRADFRI)
        set_light(hass, "light.spot_1", "off", supported_color_modes=CT)

        await apply_lighting(hass, ["light.spot_1"], transition=0.2)

        assert [c.data for c in turn_on][0] == {"entity_id": ["light.spot_1"], "transition": 0.1, "brightness": 200}
        assert turn_on[1].data["color_temp_kelvin"] == 3000

    async def test_the_configured_patterns_replace_the_defaults(self, hass: HomeAssistant):
        await setup_zones_entry(hass, options={CONF_TWO_STEP_MODELS: "*weird bulb*"})
        turn_on = async_mock_service(hass, "light", "turn_on")
        await add_device_light(hass, "light.spot_1", manufacturer="IKEA", model=TRADFRI)
        set_light(hass, "light.spot_1", "off", supported_color_modes=CT)

        await apply_lighting(hass, ["light.spot_1"], transition=0.2)

        assert len(turn_on) == 1


class TestMinimumChange:
    """A change too small to notice isn't sent. The entry's options set it;
    a call can set its own."""

    async def test_a_small_change_is_not_sent_by_default(self, setup_integration: HomeAssistant):
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=192, color_temp_kelvin=3000)

        await apply_lighting(hass, ["light.a"])

        assert turn_on == [], "8 points off a 200 target is inside the default 5%"

    async def test_the_entrys_option_sets_it(self, hass: HomeAssistant):
        await setup_zones_entry(hass, options={CONF_MIN_BRIGHTNESS_CHANGE: 1, CONF_MIN_COLOR_TEMP_CHANGE: 0})
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=192, color_temp_kelvin=3000)

        await apply_lighting(hass, ["light.a"])

        assert len(turn_on) == 1

    async def test_a_call_can_set_its_own(self, setup_integration: HomeAssistant):
        hass = setup_integration
        turn_on = async_mock_service(hass, "light", "turn_on")
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, color_temp_kelvin=2900)

        await apply_lighting(hass, ["light.a"], min_color_temp_change=20)
        assert turn_on == [], "2900K is 11 mireds from 3000K"

        await apply_lighting(hass, ["light.a"], min_color_temp_change=0)
        assert len(turn_on) == 1
