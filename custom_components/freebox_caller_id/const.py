"""Constantes pour l'intégration Freebox Caller ID."""
from homeassistant.const import Platform

DOMAIN = "freebox_caller_id"
EVENT_INCOMING_CALL = "freebox_incoming_call"

DEFAULT_HOST = "mafreebox.freebox.fr"
APP_ID = "fr.ha.callerid"
APP_NAME = "HA CallerID"
APP_VERSION = "1.1.0"
DEVICE_NAME = "Home Assistant"

CONF_HOST = "host"
CONF_APP_TOKEN = "app_token"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 2
CONF_RINGING_TIMEOUT = "ringing_timeout"
DEFAULT_RINGING_TIMEOUT = 45

# Ajout des plateformes Home Assistant
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
