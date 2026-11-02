"""/ecommerce_white_background/create - background removal onto white."""

from .. import enums, i18n
from ..base import BomiTaskNode, api_key_input, enum_input, image_input, seed_input


class BomiEcommerceWhiteBackground(BomiTaskNode):
    FEATURE_CODE = "ECOMMERCE_WHITE_BACKGROUND"
    CREATE_PATH = "/ecommerce_white_background/create"
    NODE_KEY = "ecommerce_white_background"
    ITEM_CODES = ("IMAGE",)

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": image_input(),
                "model_option_code": enum_input("model_option_code", "modelOptionCode"),
            },
            "optional": {
                "api_key": api_key_input(),
                "seed": seed_input(),
            },
        }

    def build_request(self, api_key="", model_option_code="", **_ignored):
        return {"modelOptionCode": enums.resolve("modelOptionCode", model_option_code)}


BomiEcommerceWhiteBackground.DESCRIPTION = i18n.t("nodes.ecommerce_white_background.description")
