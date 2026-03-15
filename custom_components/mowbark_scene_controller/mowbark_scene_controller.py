import asyncio
from functools import partial
from itertools import chain
import logging
from types import MethodType
from typing import Coroutine, Generator, Any

from homeassistant.core import HomeAssistant, callback, Event, EventStateChangedData
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.const import CONF_DEVICE_ID, EVENT_STATE_CHANGED, ATTR_ENTITY_ID, SERVICE_TURN_ON, ATTR_DEVICE_ID, \
    SERVICE_TOGGLE, STATE_ON, STATE_OFF
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.components.event.const import DOMAIN as EVENT_DOMAIN
from homeassistant.components.light.const import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.zwave_js.const import DOMAIN as ZWAVEJS_DOMAIN, SERVICE_SET_CONFIG_PARAMETER, \
    ATTR_CONFIG_VALUE, ATTR_CONFIG_PARAMETER
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.components.light import ATTR_EFFECT, ATTR_BRIGHTNESS_STEP
from .const import CONF_LIGHT_ID, CONF_SCENES, WIZ_SCENE_CONTROLLER_COLOR_VALUES, SCENE_CONTROLLER_COLOR_PARAMETERS, \
    SCENE_CONTROLLER_ONOFF_PARAMETERS, SCENE_CONTROLLER_ONOFF_VALUES, ALWAYS_OFF, ALWAYS_ON, BIG_BUTTON, COLOR_GREEN, \
    COLOR_RED, CONF_SCENES_ALL

_LOGGER = logging.getLogger(__name__)


class MowbarkSceneControllerEntity(Entity):
    def __init__(self, config_entry: ConfigEntry):
        self.config_entry = config_entry
        self.scene_controller_device_id = config_entry.options[CONF_DEVICE_ID]
        self.light_id = config_entry.options[CONF_LIGHT_ID]
        self.scene_entity_ids = {}
        self.scenes = {}
        for conf in CONF_SCENES_ALL:
            if conf in config_entry.options:
                self.scenes[conf] = config_entry.options[conf]
        self._attr_unique_id = self.scene_controller_device_id
        self._attr_name = f"{config_entry.title} Manager"
        self.bright_dim_task = None
        self.bright_dim_scene_idx = None
        self.big_led_color_value = None

    def _get_scene_controller_config_entry(self) -> ConfigEntry:
        device_registry = dr.async_get(self.hass)
        scene_controller_device = device_registry.async_get(self.scene_controller_device_id)
        for scene_controller_config_entry_id in scene_controller_device.config_entries:
            return self.hass.config_entries.async_get_entry(scene_controller_config_entry_id)
        raise RuntimeError("Scene controller config entry not found")

    async def async_added_to_hass(self) -> None:
        entity_registry = er.async_get(self.hass)
        scene_controller_entities = er.async_entries_for_device(entity_registry, self.scene_controller_device_id)

        for entity in scene_controller_entities:
            if entity.domain == EVENT_DOMAIN and entity.object_id_base.startswith("Scene "):
                self.scene_entity_ids[entity.entity_id] = entity.object_id_base

        scene_controller_config_entry = self._get_scene_controller_config_entry()
        self.async_on_remove(
            scene_controller_config_entry.async_on_state_change(partial(
                self._on_scene_controller_state_changed, scene_controller_config_entry
            ))
        )
        if scene_controller_config_entry.state == ConfigEntryState.LOADED:
            await self._update_all_leds()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self.scene_entity_ids.keys(), self._async_on_scene_controller_state_changed
            )
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self.light_id, self._async_on_light_state_changed
            )
        )

        _LOGGER.info("scene controller added")

    def _set_led(self, conf_key, color_value: str | None) -> Generator[Coroutine[Any, Any, None]]:
        onoff_parameter = SCENE_CONTROLLER_ONOFF_PARAMETERS[conf_key]
        if color_value is not None:
            color_parameter = SCENE_CONTROLLER_COLOR_PARAMETERS[conf_key]
            onoff_value = SCENE_CONTROLLER_ONOFF_VALUES[ALWAYS_ON]
            yield self.hass.services.async_call(ZWAVEJS_DOMAIN, SERVICE_SET_CONFIG_PARAMETER,
                                                {ATTR_DEVICE_ID: self.scene_controller_device_id,
                                                 ATTR_CONFIG_PARAMETER: color_parameter,
                                                 ATTR_CONFIG_VALUE: color_value})
        else:
            onoff_value = SCENE_CONTROLLER_ONOFF_VALUES[ALWAYS_OFF]
        yield self.hass.services.async_call(ZWAVEJS_DOMAIN, SERVICE_SET_CONFIG_PARAMETER,
                                            {ATTR_DEVICE_ID: self.scene_controller_device_id,
                                             ATTR_CONFIG_PARAMETER: onoff_parameter,
                                             ATTR_CONFIG_VALUE: onoff_value})

    def _get_conf_color_value(self, conf_key) -> str | None:
        if conf_key in self.scenes:
            return WIZ_SCENE_CONTROLLER_COLOR_VALUES[self.scenes[conf_key]]
        return None

    def _update_scene_leds(self) -> Generator[Coroutine[Any, Any, None]]:
        for conf in CONF_SCENES:
            yield from self._set_led(conf, self._get_conf_color_value(conf))

    def _update_big_led_internal(self, color_value: str | None) -> Generator[Coroutine[Any, Any, None]]:
        yield from self._set_led(BIG_BUTTON, color_value)

    async def _update_big_led(self, color_value: str | None) -> None:
        self.big_led_color_value = color_value
        await asyncio.gather(*self._update_big_led_internal(color_value))

    async def _update_all_leds(self) -> None:
        await asyncio.gather(*chain(self._update_big_led_internal(self.big_led_color_value), self._update_scene_leds()))

    def _on_scene_controller_state_changed(self, scene_controller_config_entry: ConfigEntry) -> None:
        if scene_controller_config_entry.state == ConfigEntryState.LOADED:
            self.hass.create_task(self._update_all_leds())

    async def _async_bright_dim_loop(self, step) -> None:
        while True:
            await self.hass.services.async_call(LIGHT_DOMAIN, SERVICE_TURN_ON,
                                                {ATTR_ENTITY_ID: self.light_id, ATTR_BRIGHTNESS_STEP: step})
            await asyncio.sleep(0.1)

    async def _async_key_held_down(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} held down")
        if self.bright_dim_task is not None:
            return
        if scene_idx in {1, 2}:
            step = 10
        elif scene_idx in {3, 4}:
            step = -10
        else:
            return
        self.bright_dim_scene_idx = scene_idx
        self.bright_dim_task = self.config_entry.async_create_background_task(self.hass,
                                                                              self._async_bright_dim_loop(step),
                                                                              "bright_dim_loop")

    async def _async_key_pressed(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} pressed")
        if scene_idx == 5:
            await self.hass.services.async_call(LIGHT_DOMAIN, SERVICE_TOGGLE, {ATTR_ENTITY_ID: self.light_id})
        else:
            key = f"scene_{scene_idx:03d}"
            if key in self.scenes:
                scene = self.scenes[key]
                await self.hass.services.async_call(LIGHT_DOMAIN, SERVICE_TURN_ON,
                                                    {ATTR_ENTITY_ID: self.light_id, ATTR_EFFECT: scene})

    async def _async_key_pressed2x(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} pressed 2x")
        key = f"scene_{scene_idx:03d}_x2"
        if key in self.scenes:
            scene = self.scenes[key]
            await self.hass.services.async_call(LIGHT_DOMAIN, SERVICE_TURN_ON,
                                                {ATTR_ENTITY_ID: self.light_id, ATTR_EFFECT: scene})

    async def _async_key_pressed3x(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} pressed 3x")

    async def _async_key_pressed4x(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} pressed 4x")

    async def _async_key_pressed5x(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} pressed 5x")

    async def _async_key_released(self, scene_idx: int) -> None:
        _LOGGER.info(f"scene {scene_idx} released")
        if self.bright_dim_task is not None and self.bright_dim_scene_idx == scene_idx:
            self.bright_dim_task.cancel()
            self.bright_dim_task = None
            self.bright_dim_scene_idx = None

    handlers = {
        "KeyHeldDown": _async_key_held_down,
        "KeyPressed": _async_key_pressed,
        "KeyPressed2x": _async_key_pressed2x,
        "KeyPressed3x": _async_key_pressed3x,
        "KeyPressed4x": _async_key_pressed4x,
        "KeyPressed5x": _async_key_pressed5x,
        "KeyReleased": _async_key_released
    }

    @callback
    async def _async_on_scene_controller_state_changed(self, event: Event[EventStateChangedData]) -> None:
        if event.event_type != EVENT_STATE_CHANGED:
            return
        try:
            entity_id = event.data["entity_id"]
            old_state = event.data["old_state"]
            new_state = event.data["new_state"]
            attributes = new_state.attributes
            event_type = attributes["event_type"]
            if old_state is None:
                return
            if event_type in self.handlers:
                handler = MethodType(self.handlers[event_type], self)
            else:
                _LOGGER.warning(f"Unknown event: {event_type}")
                return
            if entity_id in self.scene_entity_ids:
                original_name = self.scene_entity_ids[entity_id]
                scene_idx = int(original_name[6:])
                await handler(scene_idx)
            else:
                _LOGGER.warning(f"Unknown entity id: {entity_id}")
        except KeyError as e:
            _LOGGER.warning(f"Missing key in event: {e}")

    @callback
    async def _async_on_light_state_changed(self, event: Event[EventStateChangedData]) -> None:
        if event.event_type != EVENT_STATE_CHANGED:
            return
        try:
            new_state = event.data["new_state"].state
            if new_state == STATE_ON:
                await self._update_big_led(COLOR_GREEN)
            elif new_state == STATE_OFF:
                await self._update_big_led(COLOR_RED)
        except KeyError as e:
            _LOGGER.warning(f"Missing key in event: {e}")


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MowbarkSceneControllerEntity(config_entry)])
