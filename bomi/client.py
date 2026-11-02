"""HTTP client for the Bomi enterprise API.

Every response uses the same envelope, so a single handler covers all endpoints:

    {"code": 200, "message": "success", "data": {...},
     "timestamp": 1786932000000, "requestId": "<same as X-Request-Id>"}
"""

import json
import time

import requests

from . import config, i18n, log, request_id as rid
from .errors import BomiApiError, BomiError, BomiNetworkError, BomiTimeoutError

JSON_CONTENT_TYPE = "application/json;charset=UTF-8"

CAPABILITY_PATH = "/capability/check"
TASK_SEARCH_PATH = "/task/search"

TERMINAL_STATUSES = ("COMPLETED", "FAILED")
HEARTBEAT_SECONDS = 30

# The spec's ceiling for one /task/search query.
TASK_SEARCH_BATCH = 8


def _progress_bar(total):
    """comfy.utils.ProgressBar when running inside ComfyUI, otherwise a no-op."""
    try:
        from comfy.utils import ProgressBar
        return ProgressBar(total)
    except Exception:
        return None


def _check_interrupt():
    """Let ComfyUI's Cancel button break out of a poll loop."""
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except Exception:
        return
    throw_exception_if_processing_interrupted()


class BomiClient:
    def __init__(self, api_key, base_url=None, session=None, sleep=None):
        self.api_key = api_key or ""
        self.base_url = (base_url or config.base_url()).rstrip("/")
        self._session = session
        self._sleep = sleep or time.sleep

    # ------------------------------------------------------------------ plumbing

    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _headers(self, request_id, content_type=None, extra=None):
        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "X-Request-Id": request_id,
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if extra:
            headers.update(extra)
        return headers

    def _log_request(self, method, path, request_id, body_summary):
        log.info(
            "-> %s %s%s requestId=%s auth=%s",
            method, self.base_url, path, request_id, log.redact_key(self.api_key),
        )
        if body_summary and config.get("logRequestBodies", True):
            log.info("   request=%s", body_summary)

    def _log_response(self, path, request_id, status, elapsed_ms, envelope):
        code = envelope.get("code") if isinstance(envelope, dict) else None
        message = envelope.get("message") if isinstance(envelope, dict) else None
        log.info(
            "<- %s http=%s code=%s message=%s elapsed=%dms requestId=%s",
            path, status, code, message, elapsed_ms, request_id,
        )

    def _parse(self, response, path, request_id):
        """Validate the envelope and return `data`, raising on any non-200 code."""
        try:
            envelope = response.json()
        except ValueError:
            log.error(
                "<- %s http=%s returned non-JSON body: %s",
                path, response.status_code, (response.text or "")[:500],
            )
            raise BomiNetworkError(i18n.t("errors.badJson", path=path))

        if not isinstance(envelope, dict):
            raise BomiNetworkError(i18n.t("errors.badJson", path=path))

        code = envelope.get("code")
        if code != 200:
            error = BomiApiError(code, envelope.get("message", ""), envelope.get("data"), path)
            error.log_detail()
            raise error

        returned_id = envelope.get("requestId")
        if returned_id and returned_id != request_id:
            log.warn(
                "%s echoed requestId=%s but we sent X-Request-Id=%s",
                path, returned_id, request_id,
            )
        return envelope.get("data")

    def _send(self, method, path, request_id, body_summary, attempts=None, timeout=None, **kwargs):
        """One request plus retries.

        Every logical request gets its own X-Request-Id, but the retries of one
        request deliberately replay it: a create that reached the server and then
        lost its response must be deduplicated, not charged a second time.

        `attempts` and `timeout` override the config for one call. The option-list
        endpoints need that: they are fetched while the ComfyUI frontend waits for
        /object_info, where the default 3 tries at 60 s each would read as a hang.
        """
        url = self.base_url + path
        attempts = max(1, int(attempts if attempts is not None else config.get("maxRetries", 3)))
        timeout = timeout if timeout is not None else config.get("requestTimeoutSeconds", 60)
        verify = bool(config.get("verifySsl", True))

        last_error = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                backoff = min(2 ** (attempt - 1), 8)
                log.warn("retry %d/%d for %s in %ds (same requestId=%s)", attempt, attempts, path, backoff, request_id)
                self._sleep(backoff)

            self._log_request(method, path, request_id, body_summary if attempt == 1 else None)
            started = time.time()
            try:
                response = self.session.request(method, url, timeout=timeout, verify=verify, **kwargs)
            except requests.RequestException as exc:
                last_error = BomiNetworkError(i18n.t("errors.network", url=url, reason=exc))
                log.error("!! %s transport error: %s", path, exc)
                continue

            elapsed_ms = int((time.time() - started) * 1000)

            if response.status_code >= 500:
                last_error = BomiNetworkError(
                    i18n.t("errors.httpStatus", status=response.status_code, path=path)
                )
                log.error("!! %s http=%s elapsed=%dms", path, response.status_code, elapsed_ms)
                continue

            try:
                envelope = response.json() if response.content else {}
            except ValueError:
                envelope = {}
            self._log_response(path, request_id, response.status_code, elapsed_ms, envelope)

            try:
                return self._parse(response, path, request_id)
            except BomiApiError as exc:
                if exc.retryable and attempt < attempts:
                    last_error = exc
                    continue
                raise

        raise last_error if last_error else BomiNetworkError(i18n.t("errors.network", url=url, reason="unknown"))

    # ------------------------------------------------------------------ endpoints

    def post_json(self, path, payload, request_id=None, extra_headers=None,
                  attempts=None, timeout=None):
        request_id = request_id or rid.new_id()
        body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._send(
            "POST", path, request_id,
            log.compact_json(payload),
            attempts=attempts, timeout=timeout,
            headers=self._headers(request_id, JSON_CONTENT_TYPE, extra_headers),
            data=body,
        )

    def post_multipart(self, path, request_obj=None, image_bytes=None,
                       image_mime="image/png", image_filename="image.png", request_id=None):
        """multipart/form-data with an `image` part and a JSON `request` part.

        The `image` part is omitted entirely when image_bytes is None, for features
        that take no image input. An empty request is sent as `{}`.
        """
        request_json = json.dumps(
            request_obj if request_obj is not None else {},
            ensure_ascii=False, separators=(",", ":"),
        )
        request_id = request_id or rid.new_id()

        files = []
        if image_bytes is not None:
            files.append(("image", (image_filename, image_bytes, image_mime)))
        files.append(("request", (None, request_json, "application/json")))

        summary = "%s image=%s" % (
            log.compact_json(request_obj if request_obj is not None else {}),
            "%s (%d bytes, %s)" % (image_filename, len(image_bytes), image_mime) if image_bytes else "<none>",
        )
        # Content-Type is set by requests, including the multipart boundary.
        return self._send(
            "POST", path, request_id, summary,
            headers=self._headers(request_id),
            files=files,
        )

    def capability_check(self, payload, request_id=None):
        """POST /capability/check. Returns the data payload; raises on a non-200 code."""
        return self.post_json(CAPABILITY_PATH, payload, request_id)

    def create_task(self, path, request_obj=None, image_bytes=None,
                    image_mime="image/png", image_filename="image.png", request_id=None):
        """POST /<feature>/create."""
        return self.post_multipart(path, request_obj, image_bytes, image_mime, image_filename, request_id)

    def list_options(self, path, language=None, attempts=None, timeout=None):
        """POST one of the dropdown list endpoints. The body is `{}`; `data` is an array.

        The API answers in Chinese unless asked otherwise, so the header goes out only for
        English - sending nothing is how you ask for Chinese.
        """
        extra = {}
        if str(language or "").lower().startswith("en"):
            extra["Accept-Language"] = "en-US"
        return self.post_json(path, {}, extra_headers=extra or None,
                              attempts=attempts, timeout=timeout)

    def task_search(self, task_ids):
        """POST /task/search, in batches of at most TASK_SEARCH_BATCH ids.

        Each batch is a separate request and so carries its own X-Request-Id. AI Suite can
        create 4 model + 4 background tasks, which is exactly the documented ceiling, so
        this splits rather than trusting that nothing ever exceeds it.
        """
        ids = [str(t) for t in task_ids]
        merged = []
        for start in range(0, len(ids), TASK_SEARCH_BATCH):
            data = self.post_json(TASK_SEARCH_PATH,
                                  {"taskIdList": ids[start:start + TASK_SEARCH_BATCH]})
            merged.extend((data or {}).get("taskList") or [])
        return {"taskList": merged}

    # ------------------------------------------------------------------ polling

    def wait_for_tasks(self, task_ids, interval=None, timeout=None):
        """Poll /task/search until every task is COMPLETED.

        Raises BomiError on the first FAILED task and BomiTimeoutError if the
        deadline passes, logging the task IDs so they stay lookup-able either way.
        """
        task_ids = [str(t) for t in task_ids]
        interval = float(interval if interval is not None else config.get("pollIntervalSeconds", 2))
        timeout = float(timeout if timeout is not None else config.get("pollTimeoutSeconds", 600))

        pbar = _progress_bar(len(task_ids))
        deadline = time.time() + timeout
        last_status = {}
        last_heartbeat = time.time()
        polls = 0
        results = {}

        log.info(
            "polling %s for %d task(s) every %.1fs, timeout %.0fs: %s",
            TASK_SEARCH_PATH, len(task_ids), interval, timeout, ", ".join(task_ids),
        )

        while True:
            _check_interrupt()
            polls += 1
            data = self.task_search(task_ids)
            task_list = (data or {}).get("taskList") or []

            for task in task_list:
                task_id = str(task.get("taskId"))
                results[task_id] = task
                status = task.get("status")
                if last_status.get(task_id) != status:
                    log.info(
                        "   task %s [%s] status=%s",
                        task_id, task.get("featureCode") or task.get("itemCode") or "-", status,
                    )
                    last_status[task_id] = status

            for task_id in task_ids:
                task = results.get(task_id)
                if task and task.get("status") == "FAILED":
                    detail = self._failure_detail(task)
                    log.error("task %s FAILED: %s", task_id, detail)
                    raise BomiError(i18n.t("errors.taskFailed", task_id=task_id, detail=detail))

            done = [t for t in task_ids if (results.get(t) or {}).get("status") == "COMPLETED"]
            if pbar is not None:
                try:
                    pbar.update_absolute(len(done), len(task_ids))
                except Exception:
                    pass

            if len(done) == len(task_ids):
                log.info("all %d task(s) completed after %d poll(s)", len(task_ids), polls)
                return [results[t] for t in task_ids]

            now = time.time()
            if now >= deadline:
                pending = {t: (results.get(t) or {}).get("status", "UNKNOWN") for t in task_ids if t not in done}
                log.error(
                    "timed out after %.0fs; pending: %s",
                    timeout, ", ".join("%s=%s" % kv for kv in pending.items()),
                )
                raise BomiTimeoutError(
                    i18n.t("errors.timeout", seconds=int(timeout), task_ids=", ".join(pending.keys()))
                )

            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                log.info(
                    "   still waiting: %d/%d complete after %.0fs (%d polls)",
                    len(done), len(task_ids), timeout - (deadline - now), polls,
                )
                last_heartbeat = now

            self._sleep(min(interval, max(0.0, deadline - time.time())))

    @staticmethod
    def _failure_detail(task):
        """Localize a failed task's errorCode when it is one the spec documents."""
        from .errors import KNOWN_CODES

        code = task.get("errorCode")
        message = task.get("errorMessage") or ""
        try:
            numeric = int(code)
        except (TypeError, ValueError):
            numeric = None
        if numeric in KNOWN_CODES:
            return "%s (errorCode=%s)" % (i18n.t("errors.%d" % numeric), code)
        if code or message:
            return "errorCode=%s errorMessage=%s" % (code if code is not None else "-", message or "-")
        return i18n.t("errors.unknown", code="-", message="-")
