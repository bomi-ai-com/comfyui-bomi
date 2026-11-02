"""Logging that lands in the ComfyUI console."""

import json
import logging

PREFIX = "[Bomi]"

_logger = logging.getLogger("comfy-bomi")
if not _logger.handlers:
    # ComfyUI configures the root logger; propagate so our lines land in its console
    # and log file. Only add a handler if nothing upstream will print for us.
    _logger.propagate = True
    if not logging.getLogger().handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def info(message, *args):
    _logger.info("%s %s", PREFIX, message % args if args else message)


def warn(message, *args):
    _logger.warning("%s %s", PREFIX, message % args if args else message)


def error(message, *args):
    _logger.error("%s %s", PREFIX, message % args if args else message)


def redact_key(api_key):
    """Render a bearer token safe to print: Bearer ***<last4>."""
    if not api_key:
        return "Bearer <missing>"
    tail = api_key[-4:] if len(api_key) > 4 else ""
    return "Bearer ***%s" % tail


def compact_json(obj, limit=2000):
    """One-line JSON for log output, truncated so a long prompt cannot flood the console."""
    try:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        text = repr(obj)
    if len(text) > limit:
        return "%s... (%d chars total)" % (text[:limit], len(text))
    return text
