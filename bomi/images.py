"""Conversion between ComfyUI IMAGE tensors and the bytes/URLs the API speaks.

A ComfyUI IMAGE is a torch tensor shaped [B, H, W, C] with float32 values in 0..1.
torch is imported lazily so the pure-logic paths stay testable without it.
"""

import io
import time

import numpy as np
import requests
from PIL import Image

from . import config, i18n, log
from .errors import BomiError, BomiValidationError

# The API accepts jpg, jpeg, and png only. Anything we upload is encoded into one
# of these, so the constraint is satisfied by construction rather than by checking.
SUPPORTED_UPLOAD_FORMATS = {
    "png": ("image/png", "PNG", ".png"),
    "jpg": ("image/jpeg", "JPEG", ".jpg"),
    "jpeg": ("image/jpeg", "JPEG", ".jpg"),
}

ALLOWED_UPLOAD_MIMES = ("image/png", "image/jpeg")

# Hard per-image upload ceiling imposed by the API.
API_MAX_UPLOAD_BYTES = 20 * 1024 * 1024

JPEG_FALLBACK_QUALITY = 92


def human_size(byte_count):
    """Byte count as a human-readable string, e.g. "24.3 MB" or "512 KB"."""
    if byte_count >= 1024 * 1024:
        return "%.1f MB" % (byte_count / (1024.0 * 1024.0))
    if byte_count >= 1024:
        return "%.0f KB" % (byte_count / 1024.0)
    return "%d bytes" % byte_count


def upload_limit():
    """Effective size ceiling. config.json may lower the API's limit, never raise it."""
    try:
        configured = int(config.get("maxUploadBytes", API_MAX_UPLOAD_BYTES))
    except (TypeError, ValueError):
        log.warn("maxUploadBytes is not a number; using the API limit of %s", human_size(API_MAX_UPLOAD_BYTES))
        return API_MAX_UPLOAD_BYTES

    if configured <= 0:
        return API_MAX_UPLOAD_BYTES
    if configured > API_MAX_UPLOAD_BYTES:
        log.warn(
            "maxUploadBytes=%d is above the API limit of %d bytes; using the API limit",
            configured, API_MAX_UPLOAD_BYTES,
        )
        return API_MAX_UPLOAD_BYTES
    return configured


def tensor_to_pil(image_tensor):
    """First frame of an IMAGE batch as an RGB PIL image."""
    if image_tensor is None:
        raise BomiValidationError(i18n.t("errors.validation.imageRequired"))

    array = np.asarray(
        image_tensor.detach().cpu().numpy() if hasattr(image_tensor, "detach") else image_tensor
    )

    if array.ndim == 4:
        if array.shape[0] > 1:
            log.warn("input is a batch of %d images; uploading only the first", array.shape[0])
        array = array[0]
    if array.ndim != 3:
        raise BomiValidationError(
            i18n.t("errors.validation.imageEncode", reason="unexpected image shape %r" % (array.shape,))
        )

    array = np.clip(array.astype(np.float32), 0.0, 1.0)
    array = (array * 255.0 + 0.5).astype(np.uint8)

    channels = array.shape[2]
    if channels == 1:
        return Image.fromarray(array[:, :, 0], mode="L").convert("RGB")
    if channels >= 3:
        # Drop any alpha: the API takes flat jpg/jpeg/png.
        return Image.fromarray(array[:, :, :3], mode="RGB")
    raise BomiValidationError(
        i18n.t("errors.validation.imageEncode", reason="unsupported channel count %d" % channels)
    )


def _encode(pil_image, pillow_format, quality=None):
    buffer = io.BytesIO()
    if pillow_format == "JPEG":
        pil_image.save(buffer, format="JPEG", quality=int(quality or JPEG_FALLBACK_QUALITY), optimize=True)
    else:
        pil_image.save(buffer, format=pillow_format, optimize=True)
    return buffer.getvalue()


def tensor_to_upload_bytes(image_tensor):
    """Encode an IMAGE for the multipart `image` part.

    Returns (bytes, mime, filename). The format is always PNG or JPEG, and the
    payload is always within the upload limit (20 MB, or lower if config.json says
    so): an oversized PNG is re-encoded as JPEG, and an image still too large after
    that is rejected here rather than sent for the server to refuse.
    """
    pil_image = tensor_to_pil(image_tensor)

    requested = str(config.get("uploadFormat", "png")).strip().lower().lstrip(".")
    if requested not in SUPPORTED_UPLOAD_FORMATS:
        log.warn(
            "uploadFormat=%r is not one of png/jpg/jpeg, which are the only formats "
            "the API accepts; using png", requested,
        )
        requested = "png"
    mime, pillow_format, extension = SUPPORTED_UPLOAD_FORMATS[requested]

    try:
        payload = _encode(pil_image, pillow_format, config.get("uploadJpegQuality", JPEG_FALLBACK_QUALITY))
    except (OSError, ValueError) as exc:
        raise BomiValidationError(i18n.t("errors.validation.imageEncode", reason=exc))

    limit = upload_limit()
    if len(payload) > limit and pillow_format != "JPEG":
        log.warn(
            "encoded %s is %s, over the %s upload limit; re-encoding as JPEG q%d",
            pillow_format, human_size(len(payload)), human_size(limit), JPEG_FALLBACK_QUALITY,
        )
        payload = _encode(pil_image, "JPEG", JPEG_FALLBACK_QUALITY)
        mime, pillow_format, extension = "image/jpeg", "JPEG", ".jpg"

    if len(payload) > limit:
        # Even as JPEG it will not fit, so the server would reject it. Say so here,
        # where the message can name the resolution the user needs to reduce.
        raise BomiValidationError(i18n.t(
            "errors.validation.imageTooLarge",
            size=human_size(len(payload)), maximum=human_size(limit),
            width=pil_image.width, height=pil_image.height,
        ))

    if mime not in ALLOWED_UPLOAD_MIMES:  # unreachable; guards future edits
        raise BomiValidationError(i18n.t("errors.validation.imageFormat", mime=mime))

    log.info(
        "upload image: %dx%d %s %s of %s allowed",
        pil_image.width, pil_image.height, mime, human_size(len(payload)), human_size(limit),
    )
    return payload, mime, "image" + extension


def _fetch(url, timeout, attempts, sleep):
    last = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            sleep(min(2 ** (attempt - 1), 8))
            log.warn("retry %d/%d downloading %s", attempt, attempts, url)
        try:
            # No Authorization header: result links are pre-signed.
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            last = exc
            log.error("download failed for %s: %s", url, exc)
    raise BomiError(i18n.t("errors.downloadFailed", url=url, reason=last))


def _pad_to(array, height, width):
    """Black-pad an [H, W, C] array up to (height, width), keeping it top-left aligned.

    Padding rather than resizing: these outputs are aspect-ratio-specific, so
    stretching them to match would corrupt the result.
    """
    pad_h = height - array.shape[0]
    pad_w = width - array.shape[1]
    if pad_h <= 0 and pad_w <= 0:
        return array
    return np.pad(array, ((0, max(0, pad_h)), (0, max(0, pad_w)), (0, 0)), mode="constant")


def urls_to_tensor(urls, item_code=""):
    """Download result images and stack them into one IMAGE batch [N, H, W, C]."""
    urls = [u for u in (urls or []) if u]
    if not urls:
        raise BomiError(i18n.t("errors.noImages", item_code=item_code or "-"))

    timeout = config.get("downloadTimeoutSeconds", 360)
    attempts = max(1, int(config.get("maxRetries", 3)))

    frames = []
    for index, url in enumerate(urls, start=1):
        started = time.time()
        content = _fetch(url, timeout, attempts, time.sleep)
        try:
            with Image.open(io.BytesIO(content)) as opened:
                pil_image = opened.convert("RGB")
        except (OSError, ValueError) as exc:
            raise BomiError(i18n.t("errors.downloadFailed", url=url, reason=exc))
        frames.append(np.asarray(pil_image, dtype=np.float32) / 255.0)
        log.info(
            "downloaded %s image %d/%d: %dx%d %d bytes in %dms",
            item_code or "result", index, len(urls),
            pil_image.width, pil_image.height, len(content),
            int((time.time() - started) * 1000),
        )

    heights = {f.shape[0] for f in frames}
    widths = {f.shape[1] for f in frames}
    if len(heights) > 1 or len(widths) > 1:
        height, width = max(heights), max(widths)
        log.warn(
            "%s images have mixed sizes %s; padding all to %dx%d",
            item_code or "result",
            sorted({(f.shape[1], f.shape[0]) for f in frames}), width, height,
        )
        frames = [_pad_to(f, height, width) for f in frames]

    batch = np.stack(frames, axis=0)

    import torch  # imported here so this module loads without torch installed
    return torch.from_numpy(np.ascontiguousarray(batch)).to(torch.float32)
