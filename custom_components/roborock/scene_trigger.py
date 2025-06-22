"""
Roborock: Custom Select + Button to trigger predefined scenes
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify

from . import EntryData
from .const import DOMAIN
from .coordinator import RoborockDataUpdateCoordinator
from .device import RoborockCoordinatedEntity
from .roborock_typing import RoborockHassDeviceInfo

_LOGGER = logging.getLogger(__name__)


# === Select Entity: Scene Selector ===

class RoborockSceneSelectEntity(RoborockCoordinatedEntity, SelectEntity):
    def __init__(
        self,
        unique_id: str,
        device_id: str,
        device_info: RoborockHassDeviceInfo,
        coordinator: RoborockDataUpdateCoordinator,
    ) -> None:
        super().__init__(device_info, coordinator, unique_id)
        self.device_id = device_id
        self._scenes: list[dict[str, Any]] = []
        self._selected_scene_name: str | None = None
        self._attr_options: list[str] = []
        self._attr_name = "Selected Scene"
        if not hasattr(self.coordinator, "selected_scenes"):
            self.coordinator.selected_scenes = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._fetch_scenes()

    async def _fetch_scenes(self):
        scenes = await self.coordinator.cloud_api.get_scenes(
            self.coordinator.user_data, self.device_id
        )
        self._scenes = scenes
        # HomeDataScene objects have attributes
        self._attr_options = [scene.name for scene in scenes]
        if scenes:
            self._selected_scene_name = scenes[0].name
        # store default selection
        self.coordinator.selected_scenes[self.device_id] = self._selected_scene_name
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        self._selected_scene_name = option
        # persist selection for trigger button access
        self.coordinator.selected_scenes[self.device_id] = option
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        return self._selected_scene_name

    def get_selected_scene_id(self) -> str | None:
        for scene in self._scenes:
            if scene.name == self._selected_scene_name:
                return scene.id
        return None


# === Button Entity: Scene Trigger ===

class RoborockSceneTriggerButton(RoborockCoordinatedEntity, ButtonEntity):
    def __init__(
        self,
        unique_id: str,
        device_id: str,
        device_info: RoborockHassDeviceInfo,
        coordinator: RoborockDataUpdateCoordinator,
    ) -> None:
        super().__init__(device_info, coordinator, unique_id)
        self.device_id = device_id
        self._attr_name = "Trigger Scene"

    async def async_press(self) -> None:
        # Retrieve selection stored by the SceneSelect entity
        scene_name = None
        if hasattr(self.coordinator, "selected_scenes"):
            scene_name = self.coordinator.selected_scenes.get(self.device_id)

        scene_id: str | None = None
        if scene_name:
            try:
                scenes = await self.coordinator.cloud_api.get_scenes(
                    self.coordinator.user_data, self.device_id
                )
                for scene in scenes:
                    if scene.name == scene_name:
                        scene_id = scene.id
                        break
            except Exception as err:
                _LOGGER.error("Error fetching scenes before execution: %s", err)

        if scene_id:
            try:
                await self.coordinator.cloud_api.execute_scene(
                    self.coordinator.user_data, int(scene_id)
                )
                _LOGGER.info("Executed Roborock scene: %s", scene_id)
            except Exception as err:
                _LOGGER.error("Error executing scene %s: %s", scene_id, err, exc_info=True)
                raise
        else:
            _LOGGER.warning("No scene selected to execute.")


# === Platform Setup ===

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    domain_data: EntryData = hass.data[DOMAIN][config_entry.entry_id]
    entities: list = []

    for device_id, device_entry_data in domain_data.get("devices").items():
        coordinator: RoborockDataUpdateCoordinator = device_entry_data["coordinator"]
        device_info = coordinator.data

        scene_selector = RoborockSceneSelectEntity(
            f"{slugify(device_info.device.name)}_selected_scene", device_id, device_info, coordinator
        )
        trigger_button = RoborockSceneTriggerButton(
            f"{slugify(device_info.device.name)}_trigger_scene", device_id, device_info, coordinator
        )

        entities.extend([scene_selector, trigger_button])

    async_add_entities(entities)
