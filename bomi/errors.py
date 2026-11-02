"""Exception types. Every message shown to the user comes from text.i18n.json."""

from . import i18n, log

# Codes documented in the API spec. Anything outside this set falls back to errors.unknown.
KNOWN_CODES = (10001, 10005, 10006, 10009, 32001, 32002, 32003, 32004, 32005, 32006, 50001)

# Retrying these is pointless: the request itself is the problem.
NON_RETRYABLE_CODES = (10001, 10005, 10006, 10009, 32001, 32002, 32003, 32004, 32005, 32006)


class BomiError(RuntimeError):
    """Base class. str() is always localized text safe to show in the ComfyUI UI."""


class BomiValidationError(BomiError):
    """A node input failed validation before any network call was made."""


class BomiNetworkError(BomiError):
    """The API was unreachable, timed out at the transport layer, or replied with non-JSON."""


class BomiTimeoutError(BomiError):
    """Tasks were accepted but did not reach a terminal state within pollTimeoutSeconds."""


class BomiApiError(BomiError):
    """The API replied with a valid envelope whose `code` was not 200."""

    def __init__(self, code, message="", data=None, path=""):
        self.code = code
        self.server_message = message or ""
        self.data = data
        self.path = path
        super().__init__(localized_code_message(code, self.server_message))

    @property
    def retryable(self):
        try:
            code = int(self.code)
        except (TypeError, ValueError):
            return False
        return code not in NON_RETRYABLE_CODES

    def field_errors(self):
        """Flatten data.errors[] from a 10001 validation reply into 'field: message' strings."""
        if not isinstance(self.data, dict):
            return []
        entries = self.data.get("errors")
        if not isinstance(entries, list):
            return []
        out = []
        for entry in entries:
            if isinstance(entry, dict):
                out.append("%s: %s" % (entry.get("field", "?"), entry.get("message", "")))
            else:
                out.append(str(entry))
        return out

    def log_detail(self):
        """Log the error the way the spec asks: errorCode plus errorMessage."""
        detail = "errorCode=%s errorMessage=%s" % (self.code, self.server_message or "-")
        fields = self.field_errors()
        if fields:
            detail += " fieldErrors=[%s]" % "; ".join(fields)
        if self.path:
            detail = "%s %s" % (self.path, detail)
        log.error(detail)
        return detail


def localized_code_message(code, server_message=""):
    """Map an API code to bilingual text, falling back to errors.unknown."""
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        numeric = None

    if numeric in KNOWN_CODES:
        return i18n.t("errors.%d" % numeric)
    return i18n.t("errors.unknown", code=code, message=server_message or "-")
