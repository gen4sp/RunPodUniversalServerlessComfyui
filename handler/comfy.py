import json
import os
import time
import urllib.parse
import requests

COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")


def check_server(url: str, retries: int = 500, delay_ms: int = 50) -> bool:
    for _ in range(retries):
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(delay_ms / 1000)
    return False


def queue_workflow(workflow: dict, client_id: str) -> dict:
    payload = {"prompt": workflow, "client_id": client_id}
    resp = requests.post(
        f"http://{COMFY_HOST}/prompt",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code == 400:
        raise ValueError(f"ComfyUI validation failed: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def get_history(prompt_id: str) -> dict:
    resp = requests.get(f"http://{COMFY_HOST}/history/{prompt_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_image_data(filename: str, subfolder: str, image_type: str) -> bytes | None:
    data = {"filename": filename, "subfolder": subfolder, "type": image_type}
    url_values = urllib.parse.urlencode(data)
    try:
        resp = requests.get(f"http://{COMFY_HOST}/view?{url_values}", timeout=60)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


