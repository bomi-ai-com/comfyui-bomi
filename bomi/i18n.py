"""Bilingual text, loaded from text.i18n.json and selected by config.json."""

import json
import os

from . import log

_TEXT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "text.i18n.json")

FALLBACK_LANGUAGE = "en"

_cache = {"mtime": None, "table": None}


def _load():
    """Load (and cache) text.i18n.json, re-reading it when the file changes on disk."""
    try:
        mtime = os.path.getmtime(_TEXT_FILE)
    except OSError:
        mtime = None
    if _cache["table"] is not None and _cache["mtime"] == mtime:
        return _cache["table"]

    table = {}
    try:
        with open(_TEXT_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        table = {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}
    except (OSError, ValueError) as exc:
        log.error("could not read %s (%s); falling back to raw text keys", _TEXT_FILE, exc)

    _cache["mtime"] = mtime
    _cache["table"] = table
    return table


def languages():
    """Every language code present in the text table."""
    codes = set()
    for entry in _load().values():
        codes.update(entry.keys())
    return sorted(codes)


def t(key, language=None, **fmt):
    """Localized string for `key`.

    Resolution order: requested language -> English -> the key itself. Missing or
    surplus format placeholders never raise; the unformatted template is returned
    instead, because a translation typo must not break a running workflow.
    """
    if language is None:
        from . import config  # imported here to avoid a circular import at module load
        language = config.get("language", FALLBACK_LANGUAGE)

    entry = _load().get(key)
    if entry is None:
        log.warn("missing text key %r in text.i18n.json", key)
        template = key
    else:
        template = entry.get(language) or entry.get(FALLBACK_LANGUAGE) or key

    if not fmt:
        return template
    try:
        return template.format(**fmt)
    except (KeyError, IndexError, ValueError):
        log.warn("text key %r could not be formatted with %r", key, sorted(fmt))
        return template


def label(input_name, language=None):
    return t("inputs.%s.label" % input_name, language=language)


def tooltip(input_name, language=None, suffix=""):
    return t("inputs.%s.tooltip%s" % (input_name, suffix), language=language)
