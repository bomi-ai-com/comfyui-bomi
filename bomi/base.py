"""Shared node behaviour: the check -> create -> poll -> download roundtrip.

Subclasses declare which feature they are and how to build the `request` body;
everything else lives here so the four node modules stay declarative.
"""

import time

from . import config, enums, i18n, images, log, options, request_id as rid
from .client import BomiClient
from .errors import BomiApiError, BomiError, BomiValidationError

CATEGORY = "Bomi"

RATIOS = ["1:1", "9:16", "16:9"]
COUNTS = ["1", "2", "3", "4"]

SEED_MAX = 0xFFFFFFFFFFFFFFFF


# --------------------------------------------------------------------- input specs

def styled(name, type_spec, tooltip_suffix="", **extra):
    """An INPUT_TYPES entry carrying its localized label and tooltip."""
    spec = {"label": i18n.label(name), "tooltip": i18n.tooltip(name, suffix=tooltip_suffix)}
    spec.update(extra)
    return (type_spec, spec)


def image_input():
    return styled("image", "IMAGE")


def api_key_input():
    return styled("api_key", "STRING", default="", multiline=False)


def prompt_input(name, default=""):
    """A free-text field. Every one the API still takes is optional and capped."""
    return styled(name, "STRING", default=default, multiline=True)


def count_input(name):
    # A dropdown of strings rather than an INT widget, per the spec's "dropdown".
    return styled(name, list(COUNTS), default="1")


def seed_input():
    """A widget that is never sent to the API; its only job is to change the cache key.

    ComfyUI caches node outputs across queued prompts, so clicking Run twice on an
    unchanged graph never calls us at all. A changed seed changes the node's input
    signature, which is what lets a repeat Run reach the API.

    Declare it last of *all* a node's inputs - after everything in `optional`, not at the
    end of `required`. The frontend lists required widgets before optional ones and
    serializes their values into a positional `widgets_values` array, so a widget added
    anywhere but the very end shifts every later value onto the wrong input: a workflow
    saved before this seed existed would hand `api_key`'s empty string to the seed, and
    ComfyUI would reject the prompt with int('').
    """
    options = {"default": 0, "min": 0, "max": SEED_MAX}
    if config.get("seedControlAfterGenerate", True):
        # The frontend's control widget defaults to 'randomize' and the backend
        # cannot override that, so this means a fresh billed job on every Run.
        options["control_after_generate"] = True
    return styled("seed", "INT", **options)


def option_input(name, source, group=None, optional=False):
    """A dropdown whose entries are fetched from the API - see bomi/options.py.

    The choices are read here, inside INPUT_TYPES, which is where ComfyUI expects a combo
    to build its list (its own CheckpointLoaderSimple calls get_filename_list the same
    way). options.choices() therefore never raises: a node that cannot be declared is far
    worse than a dropdown holding a placeholder.
    """
    choices = options.choices(source, group=group, optional=optional)
    return styled(name, choices, default=choices[0])


def enum_input(name, field):
    """A dropdown of fixed constants, labelled in the configured language."""
    choices = enums.choices(field)
    return styled(name, choices, default=choices[0])


def ratio_input(name, default):
    # The default is listed first as well as passed as `default`: older ComfyUI
    # frontends take a combo's first entry as its default and ignore the option.
    choices = [default] + [ratio for ratio in RATIOS if ratio != default]
    return styled(name, choices, default=default)


# --------------------------------------------------------------------- validation

def clean_text(value):
    return "" if value is None else str(value)


def validate_text(value, field, maximum):
    """Enforce the character ceiling the spec gives for each text field."""
    text = clean_text(value)
    if len(text) > maximum:
        raise BomiValidationError(
            i18n.t("errors.validation.promptTooLong", field=field, length=len(text), maximum=maximum)
        )
    return text


def validate_count(value, field, minimum=1, maximum=4):
    """Accept the dropdown's string or a raw int; return an int inside the range."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise BomiValidationError(
            i18n.t("errors.validation.countRange", field=field, minimum=minimum, maximum=maximum, value=value)
        )
    if not minimum <= number <= maximum:
        raise BomiValidationError(
            i18n.t("errors.validation.countRange", field=field, minimum=minimum, maximum=maximum, value=value)
        )
    return number


def validate_choice(value, field, choices):
    text = clean_text(value).strip()
    if text not in choices:
        raise BomiValidationError(
            i18n.t("errors.validation.choice", field=field, choices="/".join(choices), value=value)
        )
    return text


# --------------------------------------------------------------------- the node base

class BomiTaskNode:
    """Template method for a Bomi task node.

    Subclasses set FEATURE_CODE, CREATE_PATH, NODE_KEY, ITEM_CODES, RETURN_TYPES,
    RETURN_NAMES, and implement build_request().

    IS_CHANGED is deliberately not overridden: ComfyUI's default input-based cache
    already re-runs us exactly when an input changed, and hashing a full image
    tensor on every prompt would cost far more than it saves. Nothing depends on
    it either way - every request carries its own X-Request-Id, so there is no
    client-side deduplication for a cache key to line up with.
    """

    FEATURE_CODE = ""
    CREATE_PATH = ""
    NODE_KEY = ""
    ITEM_CODES = ("IMAGE",)

    CATEGORY = CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    # ------------------------------------------------------------ validation

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        """Take whatever the graph holds; build_request() does the real validation.

        Most of our dropdowns are filled from the API, so a saved graph can legitimately
        carry a value that is not in the list this server just built: a style renamed
        upstream, the list unreachable, or config.json switched language since the graph
        was saved. ComfyUI's own check would reject the whole prompt with "Value not in
        list" before any of our code runs. Declaring **kwargs turns that off - it
        "will receive *all* available inputs and all of them will skip validation as if
        specified explicitly" - which lets the node raise a message that says what to do
        about it instead.

        This is not a licence to reorder inputs. The INT coercion that broke the seed
        (int('') on a shifted widget value) happens before this hook is consulted, so the
        seed still has to be the last widget of the node.
        """
        return True

    # ------------------------------------------------------------ subclass hooks

    def build_request(self, api_key="", **kwargs):
        """The JSON body for the `request` multipart part. Validates as it goes.

        `api_key` is the already-resolved secret. It is here because resolving a
        dropdown's saved name to the id the API wants can need a list fetched from the
        API, and only execute() knows which key won.
        """
        raise NotImplementedError

    def capability_payload(self, request_obj):
        """The body for /capability/check. Defaults to just the feature code."""
        return {"featureCode": self.FEATURE_CODE}

    # ------------------------------------------------------------ display helpers

    @classmethod
    def title(cls, language=None):
        return i18n.t("nodes.%s.title" % cls.NODE_KEY, language=language)

    @classmethod
    def describe(cls, language=None):
        return i18n.t("nodes.%s.description" % cls.NODE_KEY, language=language)

    # ------------------------------------------------------------ the roundtrip

    def execute(self, image=None, api_key="", seed=0, **kwargs):
        started = time.time()

        # The key is resolved first because build_request() may need it: the id-carrying
        # dropdowns resolve their saved display name against a list fetched from the API.
        api_secret = config.resolve_api_key(api_key)
        if not api_secret:
            raise BomiValidationError(i18n.t("errors.missingApiKey"))

        request_obj = self.build_request(api_key=api_secret, **kwargs)

        image_bytes, image_mime, image_filename = images.tensor_to_upload_bytes(image)

        create_request_id = rid.new_id()
        log.info(
            "=== %s (%s) requestId=%s seed=%s ===",
            self.title(), self.FEATURE_CODE, create_request_id, seed,
        )

        client = BomiClient(api_secret)

        self._check_capability(client, self.capability_payload(request_obj))

        create_data = client.create_task(
            self.CREATE_PATH, request_obj, image_bytes, image_mime, image_filename, create_request_id
        )
        tasks = self._read_create_response(create_data)

        poll_results = client.wait_for_tasks([t["taskId"] for t in tasks])
        by_task_id = {str(t.get("taskId")): t for t in poll_results}

        outputs = tuple(
            self._collect(item_code, tasks, by_task_id) for item_code in self.ITEM_CODES
        )

        self._log_summary(create_data, poll_results, started)
        return outputs

    # ------------------------------------------------------------ steps

    def _check_capability(self, client, payload):
        """Gate on credit before spending any. Aborts the workflow on any problem."""
        try:
            data = client.capability_check(payload)
        except BomiApiError as exc:
            raise self._capability_error(exc)

        data = data or {}
        log.info(
            "capability %s: isAllowed=%s isSufficient=%s requiredPoints=%s availablePoints=%s lackPoints=%s",
            payload.get("featureCode"),
            data.get("isAllowed"), data.get("isSufficient"),
            data.get("requiredPoints"), data.get("availablePoints"), data.get("lackPoints"),
        )
        for item in data.get("itemList") or []:
            log.info(
                "   item %s x%s @ %s = %s points",
                item.get("itemCode"), item.get("quantity"),
                item.get("unitPoints"), item.get("subtotalPoints"),
            )

        if not data.get("isAllowed"):
            raise BomiError(i18n.t("errors.featureNotEnabled"))
        if not data.get("isSufficient"):
            raise BomiError(i18n.t("errors.insufficientCredits"))
        return data

    @staticmethod
    def _capability_error(exc):
        """Map a failed /capability/check onto the messages the spec names.

        32001 -> feature not enabled, 32003 -> insufficient credits. Any other
        documented code keeps its own table message (10005/10006 are already about
        the key); an undocumented code falls back to "Invalid API Key" as the spec
        says. The real errorCode was logged by BomiApiError.log_detail() either way.
        """
        from .errors import KNOWN_CODES

        try:
            code = int(exc.code)
        except (TypeError, ValueError):
            code = None

        if code == 32001:
            return BomiError(i18n.t("errors.featureNotEnabled"))
        if code == 32003:
            return BomiError(i18n.t("errors.insufficientCredits"))
        if code in KNOWN_CODES:
            return exc
        return BomiError(i18n.t("errors.invalidKey"))

    def _read_create_response(self, data):
        """Pull the accepted task list out of a create reply, logging everything."""
        data = data or {}
        task_list = data.get("taskList") or []
        fail_items = data.get("failItems") or []

        log.info(
            "created %s: successCount=%s failCount=%s chargedPoints=%s availablePoints=%s",
            data.get("featureCode") or self.FEATURE_CODE,
            data.get("successCount"), data.get("failCount"),
            data.get("chargedPoints"), data.get("availablePoints"),
        )
        for task in task_list:
            log.info(
                "   task itemNo=%s itemCode=%s taskId=%s status=%s chargedPoints=%s",
                task.get("itemNo"), task.get("itemCode"),
                task.get("taskId"), task.get("status"), task.get("chargedPoints"),
            )
        if fail_items:
            log.error("failItems=%s", log.compact_json(fail_items))

        accepted = [
            {
                "taskId": str(t.get("taskId")),
                "itemCode": t.get("itemCode") or (self.ITEM_CODES[0] if self.ITEM_CODES else "IMAGE"),
                "itemNo": t.get("itemNo") if isinstance(t.get("itemNo"), int) else 0,
            }
            for t in task_list
            if t.get("taskId")
        ]

        if not accepted:
            detail = "successCount=%s failCount=%s failItems=%s" % (
                data.get("successCount"), data.get("failCount"), log.compact_json(fail_items),
            )
            raise BomiError(i18n.t("errors.createFailed", detail=detail))
        return accepted

    def _collect(self, item_code, tasks, by_task_id):
        """Download every image belonging to one output slot as a single IMAGE batch."""
        if len(self.ITEM_CODES) == 1:
            # Single-output node: take every task, whatever itemCode the API used.
            selected = list(tasks)
        else:
            selected = [t for t in tasks if t["itemCode"] == item_code]

        selected.sort(key=lambda t: t["itemNo"])

        urls = []
        for task in selected:
            result = by_task_id.get(task["taskId"]) or {}
            urls.extend(result.get("imageUrlList") or [])

        if not urls:
            raise BomiError(i18n.t("errors.noImages", item_code=item_code))
        return images.urls_to_tensor(urls, item_code)

    @staticmethod
    def _log_summary(create_data, poll_results, started):
        def total(field):
            values = [t.get(field) for t in poll_results if isinstance(t.get(field), (int, float))]
            return sum(values) if values else None

        available = None
        for task in poll_results:
            if isinstance(task.get("availablePoints"), (int, float)):
                available = task["availablePoints"]
        if available is None and isinstance(create_data, dict):
            available = create_data.get("availablePoints")

        log.info(
            "=== done in %.1fs: chargedPoints=%s refundedPoints=%s netPoints=%s availablePoints=%s ===",
            time.time() - started, total("chargedPoints"), total("refundedPoints"),
            total("netPoints"), available,
        )
