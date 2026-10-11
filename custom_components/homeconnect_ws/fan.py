"""Fan entities."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, NamedTuple

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.percentage import percentage_to_ranged_value, ranged_value_to_percentage
from homeconnect_websocket.message import Action, Message

from .const import DOMAIN
from .entity import HCEntity
from .helpers import create_entities, error_decorator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeconnect_websocket.entities import Entity as HcEntity
    from homeconnect_websocket.entities import Program

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCFanEntityDescription

PARALLEL_UPDATES = 0

# local patch: hoods expose the fan speed as options of the (startOnly) Venting
# program. A POST to /ro/values is acknowledged but ignored, and so is venting
# level 0; the speed has to be sent as program option and "off" is power off.
# The appliance also sends no NOTIFY for the levels on power off, so the fan
# state follows the power state when the description names one.
POWER_STATE_ON = "On"
POWER_STATE_OFF = "Off"


class SpeedMapping(NamedTuple):
    """Mapping of entity name / value and speed."""

    entity_name: str
    entity_value: int
    speed: int


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up fan platform."""
    entities = create_entities({"fan": HCFan}, config_entry.runtime_data)
    async_add_entites(entities)


class HCFan(HCEntity, FanEntity):
    """Fan Entity."""

    entity_description: HCFanEntityDescription
    _speed_entities: dict[str, HcEntity] | None = None
    _speed_range: range = None
    _speed_mapping: list[SpeedMapping]
    _power_entity: HcEntity | None = None
    _program: Program | None = None

    def __init__(
        self,
        entity_description: HCFanEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )
        self._speed_mapping = []
        self._speed_entities = {}
        self._attr_speed_count = 0
        for entity_name in entity_description.entities:
            entity = self._runtime_data.appliance.entities[entity_name]
            self._speed_entities[entity_name] = entity
            for option in entity.enum:
                if option != 0:
                    self._attr_speed_count += 1
                    self._speed_mapping.append(
                        SpeedMapping(
                            entity_name=entity_name,
                            entity_value=option,
                            speed=self._attr_speed_count,
                        )
                    )

        self._speed_range = (1, self._attr_speed_count)

        # local patch: hood support, see module comment
        if entity_description.power_entity:
            self._power_entity = self._runtime_data.appliance.entities[
                entity_description.power_entity
            ]
            # follow the power state in HA (callback registration)
            self._entities.append(self._power_entity)
        if entity_description.program:
            self._program = self._runtime_data.appliance.programs[entity_description.program]

    @property
    def _power_is_off(self) -> bool:
        """True when the power state is known and not 'On'."""
        return (
            self._power_entity is not None
            and self._power_entity.value is not None
            and self._power_entity.value != POWER_STATE_ON
        )

    @property
    def percentage(self) -> int | None:
        if self._power_is_off:
            return 0
        for speed in self._speed_mapping:
            if self._speed_entities[speed.entity_name].value_raw == speed.entity_value:
                return ranged_value_to_percentage(self._speed_range, speed.speed)
        return 0

    async def _async_send_levels(self, data: list[dict[str, Any]]) -> None:
        """Send the level values, as program options when the description has a program."""
        if self._program is not None:
            await self._program.start(
                options={item["uid"]: item["value"] for item in data},
                override_options=True,
            )
        else:
            message = Message(
                resource="/ro/values",
                action=Action.POST,
                data=data,
            )
            await self._runtime_data.appliance.session.send_sync(message)

    @error_decorator
    async def async_set_percentage(self, percentage: int) -> None:
        new_speed = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        if new_speed == 0:
            await self.async_turn_off()
            return
        new_speed_entity: str = None
        new_speed_value: int = None
        for speed in self._speed_mapping:
            if speed.speed == new_speed:
                new_speed_entity = speed.entity_name
                new_speed_value = speed.entity_value
        if new_speed_entity:
            data = []
            for entity in self._speed_entities.values():
                if entity.name == new_speed_entity:
                    data.append({"uid": entity.uid, "value": new_speed_value})
                else:
                    data.append({"uid": entity.uid, "value": 0})
            if self._power_is_off:
                # a program can only be started on a powered appliance
                await self._power_entity.set_value(POWER_STATE_ON)
            await self._async_send_levels(data)
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="speed_invalid",
                translation_placeholders={"percentage", percentage},
            )

    @error_decorator
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if percentage is None:
            if self._power_is_off:
                # a hood starts venting at its default level on power on
                await self._power_entity.set_value(POWER_STATE_ON)
                return
            percentage = ranged_value_to_percentage(self._speed_range, 1)
        await self.async_set_percentage(percentage)

    @error_decorator
    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._program is not None and self._power_entity is not None:
            # a hood ignores venting level 0; only power off stops the fan
            await self._power_entity.set_value(POWER_STATE_OFF)
            return
        data = [{"uid": entity.uid, "value": 0} for entity in self._speed_entities.values()]
        await self._async_send_levels(data)
