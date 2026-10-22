"""The house's entry, created from configuration.yaml."""

from homeassistant.config_entries import ConfigFlow

from . import DOMAIN


class SandboxHouseFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_import(self, import_data=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Sandbox House", data={})
