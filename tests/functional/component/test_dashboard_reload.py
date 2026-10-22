"""A page open during first setup can't offer FLARE's dashboard until it
reloads: the setup summary links to a reload, a repair says the same, and
the first page to load FLARE's front end clears it."""

import re
from unittest.mock import MagicMock

from homeassistant.components.http import KEY_HASS
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.flare.const import DOMAIN
from custom_components.flare.dashboard_reload import ISSUE_ID, FrontendLoadedView

RELOAD_LINK = re.compile(r'<a href="/config/lovelace/dashboards\?flare_reload=(\w+)" target="_self">')


async def _set_up(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    light = er.async_get(hass).async_get_or_create("light", "test", "k", suggested_object_id="k")
    er.async_get(hass).async_update_entity(light.entity_id, area_id=area.id)
    hass.states.async_set(light.entity_id, "off", {}, context=Context())
    flows = hass.config_entries.flow
    result = await flows.async_init(DOMAIN, context={"source": "user"})
    result = await flows.async_configure(result["flow_id"], {"next_step_id": "schedules"})
    result = await flows.async_configure(result["flow_id"], {"layout": "home"})
    result = await flows.async_configure(result["flow_id"], {"areas": {}})
    await hass.async_block_till_done()
    return result


def _issue(hass: HomeAssistant):
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)


async def test_first_setup_links_to_a_reload_and_raises_a_repair(stub_entry_setup, automations_file, hass: HomeAssistant):
    result = await _set_up(hass)

    link = result["description_placeholders"]["reload"]
    assert RELOAD_LINK.match(link), "a real page load, not navigation within the page"
    issue = _issue(hass)
    assert issue.translation_placeholders == {"reload": link}
    assert (issue.is_fixable, issue.is_persistent) == (False, False)


async def test_each_setup_links_to_a_url_never_cached(stub_entry_setup, automations_file, hass: HomeAssistant):
    first = RELOAD_LINK.match((await _set_up(hass))["description_placeholders"]["reload"])[1]
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_remove(entry.entry_id)

    second = RELOAD_LINK.match((await _set_up(hass))["description_placeholders"]["reload"])[1]

    assert first != second


async def test_setting_up_another_area_later_raises_nothing(stub_entry_setup, automations_file, hass: HomeAssistant):
    await _set_up(hass)
    ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": {}})

    assert _issue(hass) is None


async def test_a_page_loading_flares_front_end_clears_the_repair(stub_entry_setup, automations_file, hass: HomeAssistant):
    await _set_up(hass)
    request = MagicMock()
    request.app = {KEY_HASS: hass}

    response = await FrontendLoadedView().get(request)

    assert (response.status, response.content_type) == (200, "text/javascript")
    assert response.headers["Cache-Control"] == "no-store"
    assert _issue(hass) is None
