import os
import uuid
import base64
import tempfile
import json
import websocket
import socket
import time
import traceback
from typing import Dict, Any, List

from .config import get_s3_config, resolve_output_prefs
from . import comfy
from .s3_upload import upload_via_runpod_helper, upload_file_to_s3, build_object_key


WEBSOCKET_RECONNECT_ATTEMPTS = int(os.environ.get("WEBSOCKET_RECONNECT_ATTEMPTS", 5))
WEBSOCKET_RECONNECT_DELAY_S = int(os.environ.get("WEBSOCKET_RECONNECT_DELAY_S", 3))


def _attempt_websocket_reconnect(ws_url: str, max_attempts: int, delay_s: int, initial_error: Exception):
    last_err = initial_error
    for _ in range(max_attempts):
        try:
            new_ws = websocket.WebSocket()
            new_ws.connect(ws_url, timeout=10)
            return new_ws
        except (websocket.WebSocketException, ConnectionRefusedError, socket.timeout, OSError) as e:
            last_err = e
            time.sleep(delay_s)
    raise websocket.WebSocketConnectionClosedException(
        f"Failed to reconnect websocket: {last_err}"
    )


def _encode_b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def handle(job: Dict[str, Any]) -> Dict[str, Any]:
    job_input = job.get("input", {})
    job_id = job.get("id") or str(uuid.uuid4())

    if not isinstance(job_input, dict):
        try:
            job_input = json.loads(job_input)
        except Exception:
            return {"error": "Invalid input. Expected JSON object."}

    workflow = job_input.get("workflow")
    if not workflow:
        return {"error": "Missing 'workflow' parameter"}

    # Wait for Comfy API
    if not comfy.check_server(f"http://{comfy.COMFY_HOST}/", 500, 50):
        return {"error": f"ComfyUI server ({comfy.COMFY_HOST}) not reachable."}

    # Prepare S3 and output preferences
    s3_cfg = get_s3_config(job_input)
    prefs = resolve_output_prefs(job_input)

    # Upload input images if provided (data URI or base64)
    input_images: List[Dict[str, str]] = job_input.get("images") or []
    if input_images:
        for image in input_images:
            try:
                name = image["name"]
                image_data_uri = image["image"]
                base64_data = image_data_uri.split(",", 1)[1] if "," in image_data_uri else image_data_uri
                blob = base64.b64decode(base64_data)
                # Upload to Comfy /upload/image
                import requests
                from io import BytesIO

                files = {
                    "image": (name, BytesIO(blob), "image/png"),
                    "overwrite": (None, "true"),
                }
                resp = requests.post(f"http://{comfy.COMFY_HOST}/upload/image", files=files, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                return {"error": f"Failed to upload input image {image.get('name','unknown')}: {e}"}

    client_id = str(uuid.uuid4())
    ws = None
    output_data: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        ws_url = f"ws://{comfy.COMFY_HOST}/ws?clientId={client_id}"
        ws = websocket.WebSocket()
        ws.connect(ws_url, timeout=10)

        queued = comfy.queue_workflow(workflow, client_id)
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise ValueError("No prompt_id returned by ComfyUI")

        # Listen until done
        while True:
            try:
                out = ws.recv()
                if isinstance(out, str):
                    msg = json.loads(out)
                    if msg.get("type") == "executing":
                        data = msg.get("data", {})
                        if data.get("node") is None and data.get("prompt_id") == prompt_id:
                            break
                    elif msg.get("type") == "execution_error":
                        data = msg.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            errors.append(
                                f"Workflow execution error: Node Type: {data.get('node_type')}, Node ID: {data.get('node_id')}, Message: {data.get('exception_message')}"
                            )
                            break
                else:
                    continue
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException as closed_err:
                ws = _attempt_websocket_reconnect(
                    ws_url, WEBSOCKET_RECONNECT_ATTEMPTS, WEBSOCKET_RECONNECT_DELAY_S, closed_err
                )

        # Fetch outputs
        history = comfy.get_history(prompt_id)
        ph = history.get(prompt_id, {})
        outputs = ph.get("outputs", {})

        for _node_id, node_out in outputs.items():
            if "images" not in node_out:
                continue
            for img in node_out["images"]:
                filename = img.get("filename")
                subfolder = img.get("subfolder", "")
                img_type = img.get("type")
                if img_type == "temp" or not filename:
                    continue
                image_bytes = comfy.get_image_data(filename, subfolder, img_type)
                if not image_bytes:
                    errors.append(f"Failed to fetch image data for {filename}")
                    continue

                if prefs["return_base64"]:
                    output_data.append({
                        "filename": filename,
                        "type": "base64",
                        "data": _encode_b64(image_bytes)
                    })
                    continue

                # Default: upload to S3
                file_ext = os.path.splitext(filename)[1] or ".png"
                temp_file_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
                        tmp.write(image_bytes)
                        temp_file_path = tmp.name

                    # Prefer explicit S3 config via boto3 if fully provided, otherwise fallback to runpod helper
                    if all([s3_cfg.get("endpoint_url"), s3_cfg.get("access_key"), s3_cfg.get("secret_key"), s3_cfg.get("bucket")]):
                        obj_key = build_object_key(
                            prefs["default_prefix"], prefs["path_from_request"], filename
                        )
                        url = upload_file_to_s3(s3_cfg, s3_cfg["bucket"], obj_key, temp_file_path)
                    else:
                        # Backward compatible path using rp_upload (requires BUCKET_* envs)
                        url = upload_via_runpod_helper(job_id, temp_file_path)

                    output_data.append({
                        "filename": filename,
                        "type": "s3_url",
                        "data": url,
                        "key": build_object_key(prefs["default_prefix"], prefs["path_from_request"], filename)
                    })
                except Exception as e:
                    errors.append(f"Error uploading {filename}: {e}")
                finally:
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                        except OSError:
                            pass

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        try:
            if ws and ws.connected:
                ws.close()
        except Exception:
            pass

    if not output_data and errors:
        return {"error": "Job processing failed", "details": errors}

    result: Dict[str, Any] = {"images": output_data}
    if errors:
        result["errors"] = errors
    return result


