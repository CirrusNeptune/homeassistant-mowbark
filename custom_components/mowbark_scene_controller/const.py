"""Constants for the Switch as X integration."""

from typing import Final

DOMAIN: Final = "mowbark_scene_controller"

CONF_LIGHT_ID: Final = "light_id"

CONF_SCENE_001: Final = "scene_001"
CONF_SCENE_002: Final = "scene_002"
CONF_SCENE_003: Final = "scene_003"
CONF_SCENE_004: Final = "scene_004"

CONF_SCENES: Final = [CONF_SCENE_001, CONF_SCENE_002, CONF_SCENE_003, CONF_SCENE_004]
CONF_SCENES_X2: Final = [f"{scene}_x2" for scene in CONF_SCENES]
CONF_SCENES_ALL: Final = CONF_SCENES + CONF_SCENES_X2

BIG_BUTTON: Final = "big_button"

COLOR_BLUE: Final = "Blue"
COLOR_CYAN: Final = "Cyan"
COLOR_GREEN: Final = "Green"
COLOR_MAGENTA: Final = "Magenta"
COLOR_RED: Final = "Red"
COLOR_WHITE: Final = "White"
COLOR_YELLOW: Final = "Yellow"

SCENE_CONTROLLER_COLORS: Final = {
    COLOR_WHITE: 0,
    COLOR_BLUE: 1,
    COLOR_GREEN: 2,
    COLOR_RED: 3,
    COLOR_MAGENTA: 4,
    COLOR_YELLOW: 5,
    COLOR_CYAN: 6,
}

SCENE_CONTROLLER_COLOR_PARAMETERS: Final = {
    CONF_SCENE_001: 7,
    CONF_SCENE_002: 8,
    CONF_SCENE_003: 9,
    CONF_SCENE_004: 10,
    BIG_BUTTON: 6,
}

SCENE_CONTROLLER_ONOFF_PARAMETERS: Final = {
    CONF_SCENE_001: 2,
    CONF_SCENE_002: 3,
    CONF_SCENE_003: 4,
    CONF_SCENE_004: 5,
    BIG_BUTTON: 1,
}

ON_WHEN_LOAD_IS_OFF: Final = "on_when_load_is_off"
ON_WHEN_LOAD_IS_ON: Final = "on_when_load_is_on"
ALWAYS_OFF: Final = "always_off"
ALWAYS_ON: Final = "always_on"

SCENE_CONTROLLER_ONOFF_VALUES: Final = {
    ON_WHEN_LOAD_IS_OFF: 0,
    ON_WHEN_LOAD_IS_ON: 1,
    ALWAYS_OFF: 2,
    ALWAYS_ON: 3,
}

WIZ_SCENE_CONTROLLER_COLORS: Final = {
    "Alarm": COLOR_WHITE,
    "Bedtime": COLOR_YELLOW,
    "Candlelight": COLOR_YELLOW,
    "Christmas": COLOR_RED,
    "Cozy": COLOR_YELLOW,
    "Cool white": COLOR_WHITE,
    "Daylight": COLOR_WHITE,
    "Diwali": COLOR_YELLOW,
    "Deep dive": COLOR_BLUE,
    "Fall": COLOR_YELLOW,
    "Fireplace": COLOR_YELLOW,
    "Forest": COLOR_GREEN,
    "Focus": COLOR_WHITE,
    "Golden white": COLOR_WHITE,
    "Halloween": COLOR_YELLOW,
    "Jungle": COLOR_CYAN,
    "Mojito": COLOR_CYAN,
    "Night light": COLOR_YELLOW,
    "Ocean": COLOR_CYAN,
    "Party": COLOR_MAGENTA,
    "Pulse": COLOR_WHITE,
    "Pastel colors": COLOR_MAGENTA,
    "Plantgrowth": COLOR_MAGENTA,
    "Romance": COLOR_MAGENTA,
    "Relax": COLOR_YELLOW,
    "Sunset": COLOR_YELLOW,
    "Spring": COLOR_CYAN,
    "Summer": COLOR_CYAN,
    "Steampunk": COLOR_WHITE,
    "True colors": COLOR_WHITE,
    "TV time": COLOR_BLUE,
    "White": COLOR_WHITE,
    "Wake-up": COLOR_MAGENTA,
    "Warm white": COLOR_WHITE,
    "Rhythm": COLOR_WHITE,
}

WIZ_SCENE_CONTROLLER_COLOR_VALUES: Final = {
    k: SCENE_CONTROLLER_COLORS[v] for k, v in WIZ_SCENE_CONTROLLER_COLORS.items()
}
