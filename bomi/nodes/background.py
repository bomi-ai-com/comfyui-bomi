"""/background/create - generate new backgrounds for a product image."""

from .. import i18n, options
from ..base import (
    BomiTaskNode, api_key_input, count_input, image_input, option_input, seed_input,
    validate_count,
)

STYLE_SOURCE = "background_style"


class BomiBackground(BomiTaskNode):
    FEATURE_CODE = "BACKGROUND"
    CREATE_PATH = "/background/create"
    NODE_KEY = "background"
    ITEM_CODES = ("IMAGE",)

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": image_input(),
                "background_style_id": option_input("background_style_id", STYLE_SOURCE),
                "output_count": count_input("output_count"),
            },
            "optional": {
                "api_key": api_key_input(),
                "seed": seed_input(),
            },
        }

    def build_request(self, api_key="", background_style_id="", output_count="1", **_ignored):
        return {
            "backgroundStyleId": options.resolve(
                STYLE_SOURCE, background_style_id, "backgroundStyleId", api_key=api_key),
            "outputCount": validate_count(output_count, "outputCount"),
        }

    def capability_payload(self, request_obj):
        return {
            "featureCode": self.FEATURE_CODE,
            "outputCount": request_obj["outputCount"],
        }


BomiBackground.DESCRIPTION = i18n.t("nodes.background.description")
