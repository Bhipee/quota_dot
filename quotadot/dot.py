"""Dot. Open API client: push a 1-bit PNG to an Image API item."""
from __future__ import annotations

import base64
import io
import logging

import requests
from PIL import Image

from .config import env

log = logging.getLogger("quotadot")
DOT_BASE = "https://dot.mindreset.tech"


def png_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def push_image(img: Image.Image, *, task_type: str = "loop", task_key: str | None = None,
               alias: str | None = None) -> str:
    api_key = env("DOT_API_KEY")
    device_id = env("DOT_DEVICE_ID")
    if not api_key or not device_id:
        raise RuntimeError("DOT_API_KEY and DOT_DEVICE_ID are required to push")
    if not api_key.startswith("dot_app_"):
        api_key = "dot_app_" + api_key
    body = {
        "taskType": task_type,
        "refreshNow": (env("DOT_REFRESH_NOW", "true") or "true").lower() == "true",
        "image": png_base64(img),
        "border": int(env("DOT_BORDER", "0") or 0),
        "ditherType": "NONE",        # pages are already 1-bit; device dithering would blur text
    }
    if task_key:
        body["taskKey"] = task_key
    if alias:
        body["taskAlias"] = alias
    if env("DOT_LINK"):
        body["link"] = env("DOT_LINK")
    r = requests.post(
        f"{DOT_BASE}/api/authV2/open/device/{device_id}/image",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    if r.status_code != 200:
        hint = ""
        if r.status_code == 404:
            hint = (" (add an Image API item to the device's " + task_type + " list in Dot. App"
                    + (", and check the task key" if task_key else "") + ")")
        raise RuntimeError(f"Dot push failed: HTTP {r.status_code} {r.text[:200]}{hint}")
    return r.json().get("message", "ok")
