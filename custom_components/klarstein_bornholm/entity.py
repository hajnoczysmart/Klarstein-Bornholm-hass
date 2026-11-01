"""Base entity for Klarstein Bornholm."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import BornholmCoordinator


class BornholmEntity(CoordinatorEntity[BornholmCoordinator]):
    """Common device info and unique id handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BornholmCoordinator, key: str) -> None:
        super().__init__(coordinator)
        dev_id = coordinator.config_entry.data[CONF_DEVICE_ID]
        self.device = coordinator.device
        self._attr_unique_id = f"{dev_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id)},
            manufacturer="Klarstein",
            model=self.device.profile.name,
            name=f"Klarstein {self.device.profile.name}",
        )
