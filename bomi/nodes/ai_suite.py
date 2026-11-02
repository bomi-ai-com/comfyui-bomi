"""/ai_suite/create - model shots and background scenes in one call.

The create reply splits its tasks by itemCode: MODEL and BACKGROUND. Those map
to the node's two IMAGE outputs.
"""

from .. import enums, i18n, options
from ..base import (
    RATIOS, BomiTaskNode, api_key_input, count_input, enum_input, image_input,
    option_input, prompt_input, ratio_input, seed_input, validate_choice, validate_count,
    validate_text,
)

STYLE_SOURCE = "suite_style"

MODEL_PROMPT_MAX = 800
BACKGROUND_PROMPT_MAX = 600


class BomiAiSuite(BomiTaskNode):
    FEATURE_CODE = "AI_SUITE"
    CREATE_PATH = "/ai_suite/create"
    NODE_KEY = "ai_suite"
    ITEM_CODES = ("MODEL", "BACKGROUND")

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("models", "backgrounds")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": image_input(),
                "suite_style_id": option_input("suite_style_id", STYLE_SOURCE),
                "model_count": count_input("model_count"),
                "background_count": count_input("background_count"),
                "model_ratio": ratio_input("model_ratio", "9:16"),
                "background_ratio": ratio_input("background_ratio", "1:1"),
                "gender_code": enum_input("gender_code", "genderCode"),
                "jewelry_type_code": enum_input("jewelry_type_code", "jewelryTypeCode"),
                "lens_type_code": enum_input("lens_type_code", "lensTypeCode"),
                "model_extra_prompt": prompt_input("model_extra_prompt"),
                "background_extra_prompt": prompt_input("background_extra_prompt"),
            },
            "optional": {
                "api_key": api_key_input(),
                "seed": seed_input(),
            },
        }

    def build_request(self, api_key="", suite_style_id="", model_count="1",
                      background_count="1", model_ratio="9:16", background_ratio="1:1",
                      gender_code="", jewelry_type_code="", lens_type_code="",
                      model_extra_prompt="", background_extra_prompt="", **_ignored):
        return {
            "suiteStyleId": options.resolve(
                STYLE_SOURCE, suite_style_id, "suiteStyleId", api_key=api_key),
            "modelCount": validate_count(model_count, "modelCount"),
            "backgroundCount": validate_count(background_count, "backgroundCount"),
            "modelRatio": validate_choice(model_ratio, "modelRatio", RATIOS),
            "backgroundRatio": validate_choice(background_ratio, "backgroundRatio", RATIOS),
            "genderCode": enums.resolve("genderCode", gender_code),
            "jewelryTypeCode": enums.resolve("jewelryTypeCode", jewelry_type_code),
            "lensTypeCode": enums.resolve("lensTypeCode", lens_type_code),
            "modelExtraPrompt": validate_text(
                model_extra_prompt, "modelExtraPrompt", MODEL_PROMPT_MAX),
            "backgroundExtraPrompt": validate_text(
                background_extra_prompt, "backgroundExtraPrompt", BACKGROUND_PROMPT_MAX),
        }

    def capability_payload(self, request_obj):
        return {
            "featureCode": self.FEATURE_CODE,
            "modelCount": request_obj["modelCount"],
            "backgroundCount": request_obj["backgroundCount"],
        }


BomiAiSuite.DESCRIPTION = i18n.t("nodes.ai_suite.description")
