"""Tests for fan entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import call

from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    SERVICE_SET_PERCENTAGE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    FanEntityFeature,
)
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_ON,
)
from homeconnect_websocket.message import Action, Message

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeconnect_websocket.testutils import MockAppliance


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,  # noqa: ARG001
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test setting up entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state
    assert state.name == "Fake_brand HomeAppliance Fan"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Fan"
    assert (
        state.attributes[ATTR_SUPPORTED_FEATURES]
        == FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )
    assert state.attributes[ATTR_PERCENTAGE_STEP] == 25


async def test_update(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_OFF

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 25

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 50

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 0})
    await mock_appliance.entities["Test.FanSpeed2"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 75

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 0})
    await mock_appliance.entities["Test.FanSpeed2"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 100


async def test_set_speed(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test setting a speed."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan",
            ATTR_PERCENTAGE: 25,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 403, "value": 1}, {"uid": 404, "value": 0}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan",
            ATTR_PERCENTAGE: 75,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 403, "value": 0}, {"uid": 404, "value": 1}],
        )
    )


async def test_turn_on(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning on without a percentage selects the lowest speed."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 403, "value": 1}, {"uid": 404, "value": 0}],
        )
    )


async def test_hood_follows_power_state(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test the hood fan reports off while the appliance is powered off."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan_hood")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 50

    # the hood sends no NOTIFY for the levels on power off
    await mock_appliance.entities["Test.PowerState"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan_hood")
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_PERCENTAGE] == 0

    await mock_appliance.entities["Test.PowerState"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan_hood")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 50


async def test_hood_set_speed(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test setting a speed on a hood starts the program with the levels as options."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.PowerState"].update({"value": 2})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan_hood",
            ATTR_PERCENTAGE: 75,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 502,
                "options": [{"uid": 403, "value": 0}, {"uid": 404, "value": 1}],
            },
        )
    )


async def test_hood_turn_on(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning on a powered off hood."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.PowerState"].update({"value": 1})
    await hass.async_block_till_done()

    # without percentage: only power on, the hood picks its default level
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan_hood"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 200, "value": 2},
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    # with percentage: power on, then start the program with the level
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan_hood",
            ATTR_PERCENTAGE: 25,
        },
        blocking=True,
    )

    assert mock_appliance.session.send_sync.await_args_list == [
        call(
            Message(
                resource="/ro/values",
                action=Action.POST,
                data={"uid": 200, "value": 2},
            )
        ),
        call(
            Message(
                resource="/ro/activeProgram",
                action=Action.POST,
                data={
                    "program": 502,
                    "options": [{"uid": 403, "value": 1}, {"uid": 404, "value": 0}],
                },
            )
        ),
    ]


async def test_hood_turn_off(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning off a hood powers it off, as it ignores venting level 0."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.PowerState"].update({"value": 2})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan_hood"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 200, "value": 1},
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    # percentage 0 is "off" as well
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan_hood",
            ATTR_PERCENTAGE: 0,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 200, "value": 1},
        )
    )
