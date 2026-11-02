"""Layered configuration: DEFAULTS <- bomi/advanced.json <- config.json <- environment."""

import json
import os

from . import log

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_ROOT, "config.json")
EXAMPLE_FILE = os.path.join(_ROOT, "config.example.json")

# Everything that is not one of USER_KEYS, shipped inside the pack rather than put in front
# of someone installing it. See load() for how the two files layer.
ADVANCED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "advanced.json")

# The only settings an install owns. config.example.json holds exactly these three.
USER_KEYS = ("apiDomain", "enterpriseApiKey", "language")

API_PATH_PREFIX = "/api/v1/enterprise_api"

# The floor under every layer: whatever the two JSON files say, or fail to say, every key
# resolves. Both shipped files are checked against this dict by the test suite, and so are the
# inline fallbacks at each config.get() call site - those are never read, so nothing but a test
# keeps them honest.
DEFAULTS = {
    # config.json - the three an install owns (USER_KEYS)
    "apiDomain": "bomi-ai.com",
    "enterpriseApiKey": "",
    "language": "zh",
    # bomi/advanced.json - tuning, shipped with the pack
    "pollIntervalSeconds": 2,
    "pollTimeoutSeconds": 600,
    "requestTimeoutSeconds": 60,
    "downloadTimeoutSeconds": 360,
    "maxRetries": 3,
    "optionsCacheSeconds": 300,
    "optionsTimeoutSeconds": 5,
    "uploadFormat": "png",
    "uploadJpegQuality": 92,
    "maxUploadBytes": 20 * 1024 * 1024,
    "logRequestBodies": True,
    "verifySsl": True,
    "seedControlAfterGenerate": True,
}

# config.json key -> environment variable that overrides it. Exactly USER_KEYS, on purpose:
# the advanced tuning is not worth an env var each, and a setting reachable three ways is a
# setting nobody can explain the value of.
ENV_OVERRIDES = {
    "apiDomain": "BOMI_API_DOMAIN",
    "enterpriseApiKey": "BOMI_ENTERPRISE_API_KEY",
    "language": "BOMI_LANGUAGE",
}

_cache = {"mtime": None, "values": None}


def bootstrap():
    """Create config.json from config.example.json on first run. Never overwrites."""
    if os.path.exists(CONFIG_FILE) or not os.path.exists(EXAMPLE_FILE):
        return False
    try:
        with open(EXAMPLE_FILE, "r", encoding="utf-8") as src:
            content = src.read()
        with open(CONFIG_FILE, "w", encoding="utf-8") as dst:
            dst.write(content)
        log.info("created %s from config.example.json - add your enterpriseApiKey there, then "
                 "refresh the browser; this file is re-read whenever it changes, so no restart",
                 CONFIG_FILE)
        return True
    except OSError as exc:
        log.warn("could not create %s (%s); using built-in defaults", CONFIG_FILE, exc)
        return False


def _coerce(key, value):
    """Coerce an env string to the type of the corresponding default."""
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _layer(path):
    """One file's settings, or {} when it is unreadable, unparseable, or not an object.

    Never raises. config.json is hand-edited and advanced.json ships, so either can be
    malformed on a machine we will never see, and neither is worth refusing to load the pack
    over - the layer below it is always a working set of values.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            from_file = json.load(handle)
    except (OSError, ValueError) as exc:
        log.error("could not read %s (%s); using the values below it", path, exc)
        return {}
    if not isinstance(from_file, dict):
        log.warn("%s is not a JSON object; ignoring it", path)
        return {}
    # `_`-prefixed keys are comments, which JSON has no syntax for.
    return {key: value for key, value in from_file.items() if not str(key).startswith("_")}


def load(force=False):
    """Merged configuration, lowest precedence first:

        DEFAULTS  <-  bomi/advanced.json  <-  config.json  <-  BOMI_* environment

    config.json holds the three keys an install owns (USER_KEYS); the rest is tuning that
    ships inside the pack. Putting one of those keys in config.json still overrides
    advanced.json, and that is the supported way to change one for good - advanced.json is
    replaced by the next update, config.json never is.

    Re-reads whenever *either* file's mtime changes.
    """
    stamps = (_mtime(ADVANCED_FILE), _mtime(CONFIG_FILE))

    if not force and _cache["values"] is not None and _cache["mtime"] == stamps:
        return _cache["values"]

    values = dict(DEFAULTS)
    for path, stamp in zip((ADVANCED_FILE, CONFIG_FILE), stamps):
        if stamp is not None:
            values.update(_layer(path))

    for key, env_name in ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw not in (None, ""):
            values[key] = _coerce(key, raw)

    _cache["mtime"] = stamps
    _cache["values"] = values
    return values


def get(key, default=None):
    value = load().get(key, default)
    return DEFAULTS.get(key, default) if value is None else value


def reset_cache():
    """Drop the cache. Used by tests and after an in-process config change."""
    _cache["mtime"] = None
    _cache["values"] = None


def base_url():
    """https://<apiDomain>/api/v1/enterprise_api"""
    domain = str(get("apiDomain", DEFAULTS["apiDomain"])).strip().rstrip("/")
    if "://" in domain:
        scheme, _, domain = domain.partition("://")
    else:
        scheme = "https"
    return "%s://%s%s" % (scheme, domain, API_PATH_PREFIX)


def resolve_api_key(widget_value=None):
    """Non-empty node widget wins, then BOMI_ENTERPRISE_API_KEY, then config.json.

    Returns "" when nothing is configured; callers raise a localized error.
    """
    if widget_value and str(widget_value).strip():
        return str(widget_value).strip()
    return str(get("enterpriseApiKey", "") or "").strip()
