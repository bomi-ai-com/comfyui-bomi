"""The fixed-choice dropdowns: localized labels in, English constants out.

Four fields the API defines as closed sets. The spec is explicit about the split - show
the user Chinese or English according to config.json, but always submit the English
constant.

Nothing here touches the network. Unlike bomi/options.py, every label for every constant
is in text.i18n.json, so a graph built while config.json said `zh` still resolves after
someone switches it to `en`.
"""

from . import i18n
from .errors import BomiValidationError

# Request-JSON field name -> its constants, default first. The default heads the tuple
# because older ComfyUI frontends take a combo's first entry as its default and ignore
# the `default` option.
FIELDS = {
    "genderCode": ("FEMALE", "MALE", "COUPLE"),
    "jewelryTypeCode": ("RING", "NECKLACE", "BRACELET", "EARRING", "COUPLE_RINGS"),
    "lensTypeCode": ("PHOTO", "PARTIAL_PHOTO"),
    "modelOptionCode": ("ALL_CATEGORY", "SILVER_JEWELRY", "GOLD_ORIGINAL", "GOLD_RICH"),
}


def default(field):
    return FIELDS[field][0]


def label(field, constant, language=None):
    return i18n.t("enums.%s.%s" % (field, constant), language=language)


def choices(field, language=None):
    """The dropdown entries, in FIELDS order, so the default comes first."""
    return [label(field, constant, language) for constant in FIELDS[field]]


def resolve(field, value):
    """A label in any language, or the constant itself, back to the constant."""
    text = "" if value is None else str(value).strip()
    if text in FIELDS[field]:
        return text
    for language in i18n.languages():
        for constant in FIELDS[field]:
            if text == label(field, constant, language).strip():
                return constant
    raise BomiValidationError(i18n.t(
        "errors.validation.choice", field=field,
        choices="/".join(choices(field)), value=value,
    ))
