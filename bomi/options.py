"""Dropdown options fetched from the API.

Three list endpoints drive five widgets. The awkward part is where ComfyUI wants them:
a combo's choices are built inside INPUT_TYPES(), a classmethod called while the frontend
waits for /object_info - so the list has to come off the network with no node instance in
scope, no access to the node's api_key widget, and no licence to hang the UI.

That splits this module in two:

    choices()  for the UI.  One attempt, short timeout, config-level key only, and it
               never raises - a broken list must degrade to a placeholder, not to a
               ComfyUI that will not start.
    resolve()  at execute time.  The node's api_key is in scope, retries are affordable,
               and a value that cannot be resolved has to produce a message the user can
               act on.

What a workflow stores is the display *name*, not the id, so resolve() is also what keeps
a saved graph working: it matches names in every language text.i18n.json knows about, then
falls back to reading the value as a literal id.
"""

import hashlib
import time

from . import config, i18n, log
from .client import BomiClient
from .errors import BomiValidationError

SOURCES = {
    "suite_style": {"path": "/ai_suite_style/list", "grouped": False},
    "background_style": {"path": "/background_style/list", "grouped": False},
    "wear_ring_option": {"path": "/wear_ring_plus_option/list", "grouped": True},
}

# The groupCode values the wear_ring_plus option list is split by, one per dropdown.
GROUPS = ("CATEGORY", "ETHNICITY", "GENDER", "ANGLE")

# A failure is cached too, and for longer than one page load, so an unreachable API cannot
# cost one timeout per source every time someone refreshes the browser. Fixing the key
# sidesteps the wait, because the key is part of the cache key.
FAILURE_TTL = 60

# (source, language, key fingerprint) -> (stored at, entries or None for a failure)
_cache = {}


def reset_cache():
    """Drop every cached list. Used by tests and after a config change."""
    _cache.clear()


# ------------------------------------------------------------------------ declarations

def _validate(source, group):
    """Refuse a source/group pairing that could never match a row.

    Both arguments are hardcoded at their call site, so getting one wrong is a programming
    error - but a silent one otherwise: a misspelled groupCode filters every row away and
    leaves the dropdown on its placeholder for good, looking exactly like an unreachable
    API.
    """
    spec = SOURCES[source]  # KeyError names the bad source
    if spec["grouped"] and group is None:
        raise KeyError("%s is split by groupCode; name one of %s"
                       % (source, ", ".join(GROUPS)))
    if group is not None:
        if not spec["grouped"]:
            raise KeyError("%s carries no groupCode" % source)
        if group not in GROUPS:
            raise KeyError("unknown groupCode %r for %s; expected one of %s"
                           % (group, source, ", ".join(GROUPS)))


# ------------------------------------------------------------------------ fetching

def _fingerprint(api_key):
    """Enough to tell two keys apart without keeping one in a cache key."""
    return hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:12]


def _normalize(data):
    """The `data` array as {id, name, groupCode} rows, dropping anything unusable."""
    rows = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        option_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not option_id or not name:
            continue
        group = item.get("groupCode")
        rows.append({
            "id": option_id,
            "name": name,
            "groupCode": str(group).strip() if group else None,
        })
    return rows


def _fetch(source, language, api_key, ui):
    path = SOURCES[source]["path"]
    client = BomiClient(api_key)
    if ui:
        # One attempt on a short clock: the frontend is blocked on this call.
        return _normalize(client.list_options(
            path, language,
            attempts=1, timeout=config.get("optionsTimeoutSeconds", 5),
        ))
    return _normalize(client.list_options(path, language))


def entries(source, language=None, api_key=None, ui=True):
    """Cached rows for one source.

    With ui=True a failure is swallowed and [] returned; with ui=False it propagates,
    because at execute time the real network error beats a vague "unknown option".
    """
    language = language or config.get("language", i18n.FALLBACK_LANGUAGE)
    secret = api_key if api_key is not None else config.resolve_api_key()
    if not secret:
        # Nothing to authenticate with, so do not even open a socket.
        return []

    key = (source, language, _fingerprint(secret))
    now = time.time()
    cached = _cache.get(key)
    if cached is not None:
        stored_at, rows = cached
        ttl = config.get("optionsCacheSeconds", 300) if rows else FAILURE_TTL
        if now - stored_at < float(ttl):
            return list(rows or [])

    try:
        rows = _fetch(source, language, secret, ui)
    except Exception as exc:  # the UI must never see a traceback from a dropdown
        log.warn("could not load the %s option list (%s); the dropdown falls back to a "
                 "placeholder until this is fixed", source, exc)
        _cache[key] = (now, None)
        if not ui:
            raise
        return []

    if not rows:
        log.warn("%s returned no options", SOURCES[source]["path"])
    else:
        names = [row["name"] for row in rows]
        if len(set(names)) != len(names):
            log.warn("%s returned duplicate names; the first id wins for each",
                     SOURCES[source]["path"])
    _cache[key] = (now, rows)
    return list(rows)


# ------------------------------------------------------------------------ the UI side

def _sentinels(key):
    """One placeholder string per language, so resolve() recognizes any of them."""
    return {i18n.t(key, language=language).strip() for language in i18n.languages()}


def choices(source, group=None, optional=False, language=None):
    """The combo entries for INPUT_TYPES. Never raises.

    An empty combo would leave the user nothing to read and nothing to pick, so an
    unloadable list still yields one entry - the placeholder resolve() rejects with
    instructions.
    """
    try:
        _validate(source, group)
    except KeyError as exc:
        # A node that cannot declare itself is worse than a broken dropdown, so this is
        # logged rather than raised - loudly, because only a code change can fix it.
        log.error("dropdown %s/%s is declared wrong: %s", source, group, exc)
        return [i18n.t("options.unavailable", language=language)]

    names = [
        row["name"] for row in entries(source, language=language, ui=True)
        if group is None or row["groupCode"] == group
    ]
    head = [i18n.t("options.notSet", language=language)] if optional else []
    if not names:
        return head + [i18n.t("options.unavailable", language=language)]
    return head + names


# ------------------------------------------------------------------------ the wire side

def _match(source, text, language, api_key, group, ui):
    for row in entries(source, language=language, api_key=api_key, ui=ui):
        if group is not None and row["groupCode"] != group:
            continue
        if text == row["name"] or text == row["id"]:
            return row["id"]
    return None


def resolve(source, value, field, api_key=None, group=None, required=True, language=None):
    """The id to submit for a dropdown's saved display name.

    Order: the "not set" entry -> this language's names -> every other language's names ->
    the value read as a literal id. The multi-language pass is what stops a graph built
    while config.json said `zh` from breaking once it says `en`; after that only a rename
    upstream can strand a value, which is what the final error is for.

    Returns None for an optional dropdown left on "not set", and the caller must then leave
    the field out of the payload rather than send it empty. This returned `""` until
    2026-08-27; an empty option id is now a value no request may carry, so returning nothing
    at all is what stops a caller from quietly sending one. Every id it does return is a
    non-empty string, so the two can never be confused.
    """
    # Unguarded on purpose: unlike choices(), nothing is waiting on this to draw a menu,
    # and a mis-declared widget should stop the run rather than quietly send nothing.
    _validate(source, group)

    text = "" if value is None else str(value).strip()
    language = language or config.get("language", i18n.FALLBACK_LANGUAGE)

    if not text or text in _sentinels("options.notSet"):
        if required:
            raise BomiValidationError(i18n.t("errors.validation.optionUnset", field=field))
        return None
    if text in _sentinels("options.unavailable"):
        raise BomiValidationError(i18n.t("errors.validation.optionUnset", field=field))

    found = _match(source, text, language, api_key, group, ui=False)
    if found:
        return found
    for other in i18n.languages():
        # A miss here is not worth failing over: the current language already answered
        # authoritatively, and these lookups are a courtesy for switched-language graphs.
        if other != language:
            found = _match(source, text, other, api_key, group, ui=True)
            if found:
                return found

    raise BomiValidationError(
        i18n.t("errors.validation.optionUnknown", field=field, value=value))
