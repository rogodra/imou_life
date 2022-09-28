"""Xonfig flow for Imou."""
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from imouapi.device import ImouDevice, ImouDiscoverService
from imouapi.exceptions import ImouException
import voluptuous as vol

from .const import (
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DISCOVERED_DEVICE,
    CONF_ENABLE_DISCOVER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPTION_API_TIMEOUT,
    OPTION_API_URL,
    OPTION_SCAN_INTERVAL,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


class ImouFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for imou."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._app_id = None
        self._app_secret = None
        self._session = None
        self._discover_service = None
        self._discovered_devices = {}
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._session = async_create_clientsession(self.hass)
        return await self.async_step_login()

    # Step: login
    async def async_step_login(self, user_input=None):
        """Ask and validate app id and app secret."""
        self._errors = {}
        if user_input is not None:
            # check if the provided credentails are working
            self._discover_service = ImouDiscoverService(
                user_input[CONF_APP_ID], user_input[CONF_APP_SECRET], self._session
            )
            valid = False
            try:
                await self._discover_service.async_connect()
                valid = True
            except ImouException as exception:
                self._errors["base"] = exception.get_title()
                _LOGGER.error(exception.to_string())
            # valid credentials provided
            if valid:
                # store app id and secret for later steps
                self._app_id = user_input[CONF_APP_ID]
                self._app_secret = user_input[CONF_APP_SECRET]
                # if discover is requested run the discover step, otherwise the manual step
                if user_input[CONF_ENABLE_DISCOVER]:
                    return await self.async_step_discover()
                else:
                    return await self.async_step_manual()
        # by default show up the form
        return self.async_show_form(
            step_id="login",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_ID): str,
                    vol.Required(CONF_APP_SECRET): str,
                    vol.Required(CONF_ENABLE_DISCOVER, default=True): bool,
                }
            ),
            errors=self._errors,
        )

    # Step: discover

    async def async_step_discover(self, user_input=None):
        """Discover devices and ask the user to select one."""
        self._errors = {}
        if user_input is not None:
            # get the device instance from the selected input
            device = self._discovered_devices[user_input[CONF_DISCOVERED_DEVICE]]
            if device is not None:
                # set the name
                name = (
                    f"{user_input[CONF_DEVICE_NAME]}"
                    if CONF_DEVICE_NAME in user_input
                    and user_input[CONF_DEVICE_NAME] != ""
                    else device.get_name()
                )
                # create the entry
                data = {
                    CONF_DEVICE_NAME: name,
                    CONF_APP_ID: self._app_id,
                    CONF_APP_SECRET: self._app_secret,
                    CONF_DEVICE_ID: device.get_device_id(),
                }
                return self.async_create_entry(title=name, data=data)
        # discover registered devices
        try:
            self._discovered_devices = (
                await self._discover_service.async_discover_devices()
            )
        except ImouException as exception:
            self._errors["base"] = exception.get_title()
            _LOGGER.error(exception.to_string())
        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DISCOVERED_DEVICE): vol.In(
                        self._discovered_devices.keys()
                    ),
                    vol.Optional(CONF_DEVICE_NAME): str,
                }
            ),
            errors=self._errors,
        )

    # Step: manual configuration

    async def async_step_manual(self, user_input=None):
        """Manually add a device by its device id."""
        self._errors = {}
        if user_input is not None:
            # check if the provided credentails are working
            device = ImouDevice(
                self._app_id,
                self._app_secret,
                user_input[CONF_DEVICE_ID],
                self._session,
            )
            valid = False
            try:
                await device.async_connect()
                await device.async_initialize()
                valid = True
            except ImouException as exception:
                self._errors["base"] = exception.get_title()
                _LOGGER.error(exception.to_string())
            # valid credentials provided, create the entry
            if valid:
                # set the name
                name = (
                    f"{user_input[CONF_DEVICE_NAME]}"
                    if CONF_DEVICE_NAME in user_input
                    and user_input[CONF_DEVICE_NAME] != ""
                    else device.get_name()
                )
                # create the entry
                data = {
                    CONF_DEVICE_NAME: name,
                    CONF_APP_ID: self._app_id,
                    CONF_APP_SECRET: self._app_secret,
                    CONF_DEVICE_ID: user_input[CONF_DEVICE_ID],
                }
                return self.async_create_entry(title=name, data=data)
        # by default show up the form again
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): str,
                    vol.Optional(CONF_DEVICE_NAME): str,
                }
            ),
            errors=self._errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return Option Handerl."""
        return ImouOptionsFlowHandler(config_entry)


class ImouOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler for imou."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPTION_SCAN_INTERVAL,
                        default=self.options.get(
                            OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): int,
                    vol.Optional(OPTION_API_URL): str,
                    vol.Optional(OPTION_API_TIMEOUT): str,
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(title="", data=self.options)
