"""/wear_ring_plus/create - render a hand wearing the ring from the input image.

Four dropdowns come from one endpoint: /wear_ring_plus_option/list returns every option
for every group in a single reply, and each widget takes the rows whose groupCode is its
own. Only CATEGORY is required; the other three may be left on "not set", which leaves
their field out of the request entirely.
"""

from .. import i18n, options
from ..base import (
    BomiTaskNode, api_key_input, image_input, option_input, prompt_input, seed_input,
    validate_text,
)

OPTION_SOURCE = "wear_ring_option"
PROMPT_MAX = 800

# widget name -> (groupCode, request field, required)
CHOICES = (
    ("category_option_id", "CATEGORY", "categoryOptionId", True),
    ("ethnicity_option_id", "ETHNICITY", "ethnicityOptionId", False),
    ("gender_option_id", "GENDER", "genderOptionId", False),
    ("angle_option_id", "ANGLE", "angleOptionId", False),
)


class BomiWearRingPlus(BomiTaskNode):
    FEATURE_CODE = "WEAR_RING_PLUS"
    CREATE_PATH = "/wear_ring_plus/create"
    NODE_KEY = "wear_ring_plus"
    ITEM_CODES = ("IMAGE",)

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls):
        inputs = {"image": image_input()}
        for name, group, _field, required in CHOICES:
            inputs[name] = option_input(name, OPTION_SOURCE, group=group,
                                        optional=not required)
        inputs["extra_prompt"] = prompt_input("extra_prompt")
        return {
            "required": inputs,
            "optional": {
                "api_key": api_key_input(),
                "seed": seed_input(),
            },
        }

    def build_request(self, api_key="", extra_prompt="", **kwargs):
        request = {}
        for name, group, field, required in CHOICES:
            option_id = options.resolve(
                OPTION_SOURCE, kwargs.get(name, ""), field,
                api_key=api_key, group=group, required=required,
            )
            # None means an optional dropdown sat on "not set", and the field is left out
            # rather than sent empty. A required one raised instead of returning.
            if option_id is not None:
                request[field] = option_id
        request["extraPrompt"] = validate_text(extra_prompt, "extraPrompt", PROMPT_MAX)
        return request


BomiWearRingPlus.DESCRIPTION = i18n.t("nodes.wear_ring_plus.description")
