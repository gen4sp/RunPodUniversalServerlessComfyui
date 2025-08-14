import runpod
from runpod.serverless.utils import upload_file_to_bucket
import json
import urllib.parse
import time
import os
import requests
import base64
from io import BytesIO
import websocket
import uuid
import tempfile
import socket
import traceback
import argparse
 

# Ensure AWS SDK checksum behavior is compatible with GCS S3-compatible API
os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = 50
# Maximum number of API check attempts
COMFY_API_AVAILABLE_MAX_RETRIES = 500
# Websocket reconnection behaviour (can be overridden through environment variables)
# NOTE: more attempts and diagnostics improve debuggability whenever ComfyUI crashes mid-job.
#   • WEBSOCKET_RECONNECT_ATTEMPTS sets how many times we will try to reconnect.
#   • WEBSOCKET_RECONNECT_DELAY_S sets the sleep in seconds between attempts.
#
# If the respective env-vars are not supplied we fall back to sensible defaults ("5" and "3").
WEBSOCKET_RECONNECT_ATTEMPTS = int(os.environ.get("WEBSOCKET_RECONNECT_ATTEMPTS", 5))
WEBSOCKET_RECONNECT_DELAY_S = int(os.environ.get("WEBSOCKET_RECONNECT_DELAY_S", 3))

# Extra verbose websocket trace logs (set WEBSOCKET_TRACE=true to enable)
if os.environ.get("WEBSOCKET_TRACE", "false").lower() == "true":
    # This prints low-level frame information to stdout which is invaluable for diagnosing
    # protocol errors but can be noisy in production – therefore gated behind an env-var.
    websocket.enableTrace(True)

# Debug mode for detailed logging (set RUNPOD_DEBUG=true to enable)
DEBUG_MODE = os.environ.get("RUNPOD_DEBUG", "false").lower() == "true"

def debug_log(message):
    """Выводит отладочную информацию только если включен DEBUG_MODE"""
    if DEBUG_MODE:
        print(f"worker-comfyui - DEBUG: {message}")

# Host where ComfyUI is running
COMFY_HOST = "127.0.0.1:8188"

# ---------------------------------------------------------------------------
# Helper: quick reachability probe of ComfyUI HTTP endpoint (port 8188)
# ---------------------------------------------------------------------------


def _comfy_server_status():
    """Return a dictionary with basic reachability info for the ComfyUI HTTP server."""
    try:
        resp = requests.get(f"http://{COMFY_HOST}/", timeout=5)
        return {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def _attempt_websocket_reconnect(ws_url, max_attempts, delay_s, initial_error):
    """
    Attempts to reconnect to the WebSocket server after a disconnect.

    Args:
        ws_url (str): The WebSocket URL (including client_id).
        max_attempts (int): Maximum number of reconnection attempts.
        delay_s (int): Delay in seconds between attempts.
        initial_error (Exception): The error that triggered the reconnect attempt.

    Returns:
        websocket.WebSocket: The newly connected WebSocket object.

    Raises:
        websocket.WebSocketConnectionClosedException: If reconnection fails after all attempts.
    """
    print(
        f"worker-comfyui - Websocket connection closed unexpectedly: {initial_error}. Attempting to reconnect..."
    )
    last_reconnect_error = initial_error
    for attempt in range(max_attempts):
        # Log current server status before each reconnect attempt so that we can
        # see whether ComfyUI is still alive (HTTP port 8188 responding) even if
        # the websocket dropped. This is extremely useful to differentiate
        # between a network glitch and an outright ComfyUI crash/OOM-kill.
        srv_status = _comfy_server_status()
        if not srv_status["reachable"]:
            # If ComfyUI itself is down there is no point in retrying the websocket –
            # bail out immediately so the caller gets a clear "ComfyUI crashed" error.
            print(
                f"worker-comfyui - ComfyUI HTTP unreachable – aborting websocket reconnect: {srv_status.get('error', 'status '+str(srv_status.get('status_code')))}"
            )
            raise websocket.WebSocketConnectionClosedException(
                "ComfyUI HTTP unreachable during websocket reconnect"
            )

        # Otherwise we proceed with reconnect attempts while server is up
        print(
            f"worker-comfyui - Reconnect attempt {attempt + 1}/{max_attempts}... (ComfyUI HTTP reachable, status {srv_status.get('status_code')})"
        )
        try:
            # Need to create a new socket object for reconnect
            new_ws = websocket.WebSocket()
            new_ws.connect(ws_url, timeout=10)  # Use existing ws_url
            print(f"worker-comfyui - Websocket reconnected successfully.")
            return new_ws  # Return the new connected socket
        except (
            websocket.WebSocketException,
            ConnectionRefusedError,
            socket.timeout,
            OSError,
        ) as reconn_err:
            last_reconnect_error = reconn_err
            print(
                f"worker-comfyui - Reconnect attempt {attempt + 1} failed: {reconn_err}"
            )
            if attempt < max_attempts - 1:
                print(
                    f"worker-comfyui - Waiting {delay_s} seconds before next attempt..."
                )
                time.sleep(delay_s)
            else:
                print(f"worker-comfyui - Max reconnection attempts reached.")

    # If loop completes without returning, raise an exception
    print("worker-comfyui - Failed to reconnect websocket after connection closed.")
    raise websocket.WebSocketConnectionClosedException(
        f"Connection closed and failed to reconnect. Last error: {last_reconnect_error}"
    )


def validate_input(job_input):
    """
    Validates the input for the handler function.

    Args:
        job_input (dict): The input data to validate.

    Returns:
        tuple: A tuple containing the validated data and an error message, if any.
               The structure is (validated_data, error_message).
    """
    # Validate if job_input is provided
    if job_input is None:
        return None, "Please provide input"

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            return None, "Invalid JSON format in input"

    # Validate 'workflow' in input
    workflow = job_input.get("workflow")
    if workflow is None:
        return None, "Missing 'workflow' parameter"

    # Validate 'images' in input, if provided
    images = job_input.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(
            "name" in image and "image" in image for image in images
        ):
            return (
                None,
                "'images' must be a list of objects with 'name' and 'image' keys",
            )

    # Validate 'videos' in input, if provided
    videos = job_input.get("videos")
    if videos is not None:
        if not isinstance(videos, list) or not all(
            "name" in video and "video" in video for video in videos
        ):
            return (
                None,
                "'videos' must be a list of objects with 'name' and 'video' keys",
            )

    # Return validated data and no error
    return {"workflow": workflow, "images": images, "videos": videos}, None


def check_server(url, retries=500, delay=50):
    """
    Check if a server is reachable via HTTP GET request

    Args:
    - url (str): The URL to check
    - retries (int, optional): The number of times to attempt connecting to the server. Default is 500
    - delay (int, optional): The time in milliseconds to wait between retries. Default is 50

    Returns:
    bool: True if the server is reachable within the given number of retries, otherwise False
    """

    print(f"worker-comfyui - Checking API server at {url}...")
    for i in range(retries):
        try:
            response = requests.get(url, timeout=5)

            # If the response status code is 200, the server is up and running
            if response.status_code == 200:
                print(f"worker-comfyui - API is reachable")
                return True
        except requests.Timeout:
            pass
        except requests.RequestException as e:
            pass

        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    print(
        f"worker-comfyui - Failed to connect to server at {url} after {retries} attempts."
    )
    return False


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.

    Returns:
        dict: A dictionary indicating success or error.
    """
    if not images:
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"worker-comfyui - Uploading {len(images)} image(s)...")

    for image in images:
        try:
            name = image["name"]
            image_data_uri = image["image"]  # Get the full string (might have prefix)

            # --- Strip Data URI prefix if present ---
            if "," in image_data_uri:
                # Find the comma and take everything after it
                base64_data = image_data_uri.split(",", 1)[1]
            else:
                # Assume it's already pure base64
                base64_data = image_data_uri
            # --- End strip ---

            blob = base64.b64decode(base64_data)  # Decode the cleaned data

            # Prepare the form data
            files = {
                "image": (name, BytesIO(blob), "image/png"),
                "overwrite": (None, "true"),
            }

            # POST request to upload the image
            response = requests.post(
                f"http://{COMFY_HOST}/upload/image", files=files, timeout=30
            )
            response.raise_for_status()

            responses.append(f"Successfully uploaded {name}")
            print(f"worker-comfyui - Successfully uploaded {name}")

        except base64.binascii.Error as e:
            error_msg = f"Error decoding base64 for {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.Timeout:
            error_msg = f"Timeout uploading {image.get('name', 'unknown')}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.RequestException as e:
            error_msg = f"Error uploading {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except Exception as e:
            error_msg = (
                f"Unexpected error uploading {image.get('name', 'unknown')}: {e}"
            )
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)

    if upload_errors:
        print(f"worker-comfyui - image(s) upload finished with errors")
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    print(f"worker-comfyui - image(s) upload complete")
    return {
        "status": "success",
        "message": "All images uploaded successfully",
        "details": responses,
    }


def upload_videos(videos):
    """
    Upload a list of base64 encoded videos to the ComfyUI server using the /upload/image endpoint.

    Args:
        videos (list): A list of dictionaries, each containing the 'name' of the video and the 'video' as a base64 encoded string.

    Returns:
        dict: A dictionary indicating success or error.
    """
    if not videos:
        return {"status": "success", "message": "No videos to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"worker-comfyui - Uploading {len(videos)} video(s)...")

    for video in videos:
        try:
            name = video["name"]
            video_data_uri = video["video"]  # Full string, may include data URI prefix

            # Strip Data URI prefix if present
            if "," in video_data_uri:
                base64_data = video_data_uri.split(",", 1)[1]
            else:
                base64_data = video_data_uri

            blob = base64.b64decode(base64_data)

            # Prepare the form data. ComfyUI accepts arbitrary files via this endpoint.
            files = {
                # Field name must be 'image' for the endpoint, even for videos
                "image": (name, BytesIO(blob), "video/mp4"),
                "overwrite": (None, "true"),
            }

            # POST request to upload the video (longer timeout for larger files)
            response = requests.post(
                f"http://{COMFY_HOST}/upload/image", files=files, timeout=120
            )
            response.raise_for_status()

            responses.append(f"Successfully uploaded {name}")
            print(f"worker-comfyui - Successfully uploaded video {name}")

        except base64.binascii.Error as e:
            error_msg = f"Error decoding base64 for {video.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.Timeout:
            error_msg = f"Timeout uploading {video.get('name', 'unknown')}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.RequestException as e:
            error_msg = f"Error uploading {video.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error uploading {video.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)

    if upload_errors:
        print(f"worker-comfyui - video(s) upload finished with errors")
        return {
            "status": "error",
            "message": "Some videos failed to upload",
            "details": upload_errors,
        }

    print(f"worker-comfyui - video(s) upload complete")
    return {
        "status": "success",
        "message": "All videos uploaded successfully",
        "details": responses,
    }


def get_available_models():
    """
    Get list of available models from ComfyUI

    Returns:
        dict: Dictionary containing available models by type
    """
    try:
        response = requests.get(f"http://{COMFY_HOST}/object_info", timeout=10)
        response.raise_for_status()
        object_info = response.json()

        # Extract available checkpoints from CheckpointLoaderSimple
        available_models = {}
        if "CheckpointLoaderSimple" in object_info:
            checkpoint_info = object_info["CheckpointLoaderSimple"]
            if "input" in checkpoint_info and "required" in checkpoint_info["input"]:
                ckpt_options = checkpoint_info["input"]["required"].get("ckpt_name")
                if ckpt_options and len(ckpt_options) > 0:
                    available_models["checkpoints"] = (
                        ckpt_options[0] if isinstance(ckpt_options[0], list) else []
                    )

        return available_models
    except Exception as e:
        print(f"worker-comfyui - Warning: Could not fetch available models: {e}")
        return {}


def queue_workflow(workflow, client_id):
    """
    Queue a workflow to be processed by ComfyUI

    Args:
        workflow (dict): A dictionary containing the workflow to be processed
        client_id (str): The client ID for the websocket connection

    Returns:
        dict: The JSON response from ComfyUI after processing the workflow

    Raises:
        ValueError: If the workflow validation fails with detailed error information
    """
    # Include client_id in the prompt payload
    payload = {"prompt": workflow, "client_id": client_id}
    data = json.dumps(payload).encode("utf-8")

    # Use requests for consistency and timeout
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        f"http://{COMFY_HOST}/prompt", data=data, headers=headers, timeout=30
    )

    # Handle validation errors with detailed information
    if response.status_code == 400:
        print(f"worker-comfyui - ComfyUI returned 400. Response body: {response.text}")
        try:
            error_data = response.json()
            print(f"worker-comfyui - Parsed error data: {error_data}")

            # Try to extract meaningful error information
            error_message = "Workflow validation failed"
            error_details = []

            # ComfyUI seems to return different error formats, let's handle them all
            if "error" in error_data:
                error_info = error_data["error"]
                if isinstance(error_info, dict):
                    error_message = error_info.get("message", error_message)
                    if error_info.get("type") == "prompt_outputs_failed_validation":
                        error_message = "Workflow validation failed"
                else:
                    error_message = str(error_info)

            # Check for node validation errors in the response
            if "node_errors" in error_data:
                for node_id, node_error in error_data["node_errors"].items():
                    if isinstance(node_error, dict):
                        for error_type, error_msg in node_error.items():
                            error_details.append(
                                f"Node {node_id} ({error_type}): {error_msg}"
                            )
                    else:
                        error_details.append(f"Node {node_id}: {node_error}")

            # Check if the error data itself contains validation info
            if error_data.get("type") == "prompt_outputs_failed_validation":
                error_message = error_data.get("message", "Workflow validation failed")
                # For this type of error, we need to parse the validation details from logs
                # Since ComfyUI doesn't seem to include detailed validation errors in the response
                # Let's provide a more helpful generic message
                available_models = get_available_models()
                if available_models.get("checkpoints"):
                    error_message += f"\n\nThis usually means a required model or parameter is not available."
                    error_message += f"\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                else:
                    error_message += "\n\nThis usually means a required model or parameter is not available."
                    error_message += "\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(error_message)

            # If we have specific validation errors, format them nicely
            if error_details:
                detailed_message = f"{error_message}:\n" + "\n".join(
                    f"• {detail}" for detail in error_details
                )

                # Try to provide helpful suggestions for common errors
                if any(
                    "not in list" in detail and "ckpt_name" in detail
                    for detail in error_details
                ):
                    available_models = get_available_models()
                    if available_models.get("checkpoints"):
                        detailed_message += f"\n\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                    else:
                        detailed_message += "\n\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(detailed_message)
            else:
                # Fallback to the raw response if we can't parse specific errors
                raise ValueError(f"{error_message}. Raw response: {response.text}")

        except (json.JSONDecodeError, KeyError) as e:
            # If we can't parse the error response, fall back to the raw text
            raise ValueError(
                f"ComfyUI validation failed (could not parse error response): {response.text}"
            )

    # For other HTTP errors, raise them normally
    response.raise_for_status()
    return response.json()


def get_history(prompt_id):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    # Use requests for consistency and timeout
    response = requests.get(f"http://{COMFY_HOST}/history/{prompt_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def get_image_data(filename, subfolder, image_type):
    """
    Fetch image bytes from the ComfyUI /view endpoint.

    Args:
        filename (str): The filename of the image.
        subfolder (str): The subfolder where the image is stored.
        image_type (str): The type of the image (e.g., 'output').

    Returns:
        bytes: The raw image data, or None if an error occurs.
    """
    print(
        f"worker-comfyui - Fetching image data: type={image_type}, subfolder={subfolder}, filename={filename}"
    )
    data = {"filename": filename, "subfolder": subfolder, "type": image_type}
    url_values = urllib.parse.urlencode(data)
    try:
        # Use requests for consistency and timeout
        response = requests.get(f"http://{COMFY_HOST}/view?{url_values}", timeout=60)
        response.raise_for_status()
        print(f"worker-comfyui - Successfully fetched image data for {filename}")
        return response.content
    except requests.Timeout:
        print(f"worker-comfyui - Timeout fetching image data for {filename}")
        return None
    except requests.RequestException as e:
        print(f"worker-comfyui - Error fetching image data for {filename}: {e}")
        return None
    except Exception as e:
        print(
            f"worker-comfyui - Unexpected error fetching image data for {filename}: {e}"
        )
        return None


def _load_gcs_bucket_creds():
    """Load GCS S3-compatible HMAC credentials.
    
    Tries the following files in order:
    - /runpod-volume/keys/gc_hmac.json (in worker)
    - /keys/gc_hmac.json (for local runs)

    Expected JSON format:
    {
        "endpoint_url": "https://storage.googleapis.com",
        "bucket": "hyper_tv",
        "aws_access_key_id": "xxx",
        "aws_secret_access_key": "xxx"
    }
    """
    primary_path = "/runpod-volume/keys/gc_hmac.json"
    fallback_path = "/keys/gc_hmac.json"
    try:
        creds_path = primary_path if os.path.exists(primary_path) else (
            fallback_path if os.path.exists(fallback_path) else None
        )
        if not creds_path:
            return None, None

        with open(creds_path, "r") as f:
            raw = json.load(f)

        endpoint_url = raw.get("endpoint_url")
        access_id = raw.get("aws_access_key_id")
        access_secret = raw.get("aws_secret_access_key")
        bucket_name = raw.get("bucket")

        if not all([endpoint_url, access_id, access_secret, bucket_name]):
            print("worker-comfyui - Incomplete GCS creds in gc_hmac.json; falling back if needed.")
            return None, None

        bucket_creds = {
            "endpointUrl": endpoint_url,
            "accessId": access_id,
            "accessSecret": access_secret,
            "bucketName": bucket_name,
        }
        return bucket_creds, bucket_name
    except Exception as e:
        print(f"worker-comfyui - Failed to load GCS creds: {e}")
        return None, None


def _handle_local_mode(job_input, upload_prefix, gcs_bucket_creds, gcs_bucket_name):
    """Local test mode: bypass ComfyUI and return image from disk.

    Respects the same output contract as normal handler: returns either base64
    or uploads to the configured bucket and returns a URL.
    """
    try:
        local_image_path = (
            job_input.get("local_image_path")
            or os.environ.get("LOCAL_IMAGE_PATH")
            or "/girs.png"
        )
        print(f"worker-comfyui - Local mode enabled. Reading image from {local_image_path}")

        if not os.path.exists(local_image_path):
            return {"error": f"Local image not found: {local_image_path}"}

        with open(local_image_path, "rb") as f:
            image_bytes = f.read()

        filename = os.path.basename(local_image_path)
        output_data = []
        errors = []

        if image_bytes:
            file_extension = os.path.splitext(filename)[1] or ".png"

            if not bool(job_input.get("return_base64", False)) and gcs_bucket_creds and gcs_bucket_name:
                try:
                    with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                        temp_file.write(image_bytes)
                        temp_file_path = temp_file.name
                    print(
                        f"worker-comfyui - [local] Uploading {filename} to bucket {gcs_bucket_name} with prefix '{upload_prefix}'..."
                    )
                    presigned_url = upload_file_to_bucket(
                        filename,
                        temp_file_path,
                        gcs_bucket_creds,
                        gcs_bucket_name,
                        upload_prefix,
                    )
                    os.remove(temp_file_path)
                    output_data.append(
                        {"filename": filename, "type": "url", "data": presigned_url}
                    )
                except Exception as e:
                    error_msg = (
                        f"Error uploading {filename} to bucket {gcs_bucket_name} "
                        f"(endpoint={gcs_bucket_creds.get('endpointUrl')}, prefix={upload_prefix}): {e}"
                    )
                    print(f"worker-comfyui - {error_msg}")
                    errors.append(error_msg)
            else:
                try:
                    base64_image = base64.b64encode(image_bytes).decode("utf-8")
                    output_data.append(
                        {"filename": filename, "type": "base64", "data": base64_image}
                    )
                except Exception as e:
                    error_msg = f"Error encoding {filename} to base64: {e}"
                    print(f"worker-comfyui - {error_msg}")
                    errors.append(error_msg)
        else:
            error_msg = f"Failed to read local image bytes from {local_image_path}"
            print(f"worker-comfyui - {error_msg}")
            errors.append(error_msg)

        final_result = {}
        if output_data:
            final_result["images"] = output_data
        if errors:
            final_result["errors"] = errors

        if not output_data and errors:
            return {"error": "Job processing failed", "details": errors}
        elif not output_data and not errors:
            final_result["status"] = "success_no_images"
            final_result["images"] = []

        print(f"worker-comfyui - [local] Completed. Returning {len(output_data)} image(s).")
        return final_result
    except Exception as e:
        print(f"worker-comfyui - Local mode error: {e}")
        print(traceback.format_exc())
        return {"error": f"Local mode error: {e}"}


def handler(job):
    """
    Handles a job using ComfyUI via websockets for status and image retrieval.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    print(f"worker-comfyui - Handler called with job ID: {job.get('id', 'unknown')}")
    print(f"worker-comfyui - Job input keys: {list(job.get('input', {}).keys())}")
    
    # Логируем время начала обработки
    start_time = time.time()
    print(f"worker-comfyui - Processing started at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
    
    try:
        job_input = job["input"]
        job_id = job["id"]
        
        # Логируем основные параметры запроса (без чувствительных данных)
        safe_input = {k: (str(v)[:200] + "..." if len(str(v)) > 200 else v) 
                     for k, v in job_input.items() 
                     if k not in ["workflow", "images"]}  # Исключаем большие объекты
        if "workflow" in job_input:
            safe_input["workflow_keys"] = list(job_input["workflow"].keys()) if isinstance(job_input["workflow"], dict) else "non-dict"
        if "images" in job_input:
            safe_input["images_count"] = len(job_input["images"]) if isinstance(job_input["images"], list) else "non-list"
        
        print(f"worker-comfyui - Job input summary: {json.dumps(safe_input, indent=2)}")
        
    except KeyError as e:
        error_msg = f"Missing required job field: {e}"
        print(f"worker-comfyui - ERROR: {error_msg}")
        print(f"worker-comfyui - Full job data: {job}")
        print(traceback.format_exc())
        return {"error": error_msg}

    # Optional output controls and upload prefix for both remote and local flows
    return_base64 = bool(job_input.get("return_base64", False))
    path_from_request = job_input.get("path") or ""
    path_from_request = str(path_from_request).strip().strip("/")
    upload_prefix = "rp" if not path_from_request else f"rp/{path_from_request}"
    gcs_bucket_creds, gcs_bucket_name = _load_gcs_bucket_creds()

    # Local test mode: bypass ComfyUI network calls
    if job_input.get("local", False) or os.environ.get("LOCAL_MODE", "false").lower() == "true":
        return _handle_local_mode(job_input, upload_prefix, gcs_bucket_creds, gcs_bucket_name)

    # Validate input for remote (ComfyUI) flow
    validated_data, error_message = validate_input(job_input)
    if error_message:
        return {"error": error_message}

    workflow = validated_data["workflow"]
    input_images = validated_data.get("images")
    input_videos = validated_data.get("videos")

    # Make sure that the ComfyUI HTTP API is available before proceeding
    if not check_server(
        f"http://{COMFY_HOST}/",
        COMFY_API_AVAILABLE_MAX_RETRIES,
        COMFY_API_AVAILABLE_INTERVAL_MS,
    ):
        return {
            "error": f"ComfyUI server ({COMFY_HOST}) not reachable after multiple retries."
        }

    # Upload input images if they exist
    if input_images:
        upload_result = upload_images(input_images)
        if upload_result["status"] == "error":
            # Return upload errors
            return {
                "error": "Failed to upload one or more input images",
                "details": upload_result["details"],
            }

    # Upload input videos if they exist
    if input_videos:
        upload_result = upload_videos(input_videos)
        if upload_result["status"] == "error":
            return {
                "error": "Failed to upload one or more input videos",
                "details": upload_result["details"],
            }

    ws = None
    client_id = str(uuid.uuid4())
    prompt_id = None
    output_data = []
    errors = []

    try:
        # Establish WebSocket connection
        ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"
        print(f"worker-comfyui - Connecting to websocket: {ws_url}")
        ws = websocket.WebSocket()
        ws.connect(ws_url, timeout=10)
        print(f"worker-comfyui - Websocket connected")

        # Queue the workflow
        try:
            debug_log(f"Queuing workflow with client_id: {client_id}")
            debug_log(f"Workflow has {len(workflow)} nodes")
            queued_workflow = queue_workflow(workflow, client_id)
            prompt_id = queued_workflow.get("prompt_id")
            if not prompt_id:
                raise ValueError(
                    f"Missing 'prompt_id' in queue response: {queued_workflow}"
                )
            print(f"worker-comfyui - Queued workflow with ID: {prompt_id}")
            debug_log(f"Queue response: {queued_workflow}")
        except requests.RequestException as e:
            print(f"worker-comfyui - Error queuing workflow: {e}")
            raise ValueError(f"Error queuing workflow: {e}")
        except Exception as e:
            print(f"worker-comfyui - Unexpected error queuing workflow: {e}")
            # For ValueError exceptions from queue_workflow, pass through the original message
            if isinstance(e, ValueError):
                raise e
            else:
                raise ValueError(f"Unexpected error queuing workflow: {e}")

        # Wait for execution completion via WebSocket
        print(f"worker-comfyui - Waiting for workflow execution ({prompt_id})...")
        execution_done = False
        while True:
            try:
                out = ws.recv()
                debug_log(f"Received websocket message: {str(out)[:500]}...")
                if isinstance(out, str):
                    message = json.loads(out)
                    debug_log(f"Parsed message type: {message.get('type')}")
                    if message.get("type") == "status":
                        status_data = message.get("data", {}).get("status", {})
                        print(
                            f"worker-comfyui - Status update: {status_data.get('exec_info', {}).get('queue_remaining', 'N/A')} items remaining in queue"
                        )
                    elif message.get("type") == "executing":
                        data = message.get("data", {})
                        if (
                            data.get("node") is None
                            and data.get("prompt_id") == prompt_id
                        ):
                            print(
                                f"worker-comfyui - Execution finished for prompt {prompt_id}"
                            )
                            execution_done = True
                            break
                    elif message.get("type") == "execution_error":
                        data = message.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            error_details = f"Node Type: {data.get('node_type')}, Node ID: {data.get('node_id')}, Message: {data.get('exception_message')}"
                            print(
                                f"worker-comfyui - Execution error received: {error_details}"
                            )
                            errors.append(f"Workflow execution error: {error_details}")
                            break
                else:
                    continue
            except websocket.WebSocketTimeoutException:
                print(f"worker-comfyui - Websocket receive timed out. Still waiting...")
                continue
            except websocket.WebSocketConnectionClosedException as closed_err:
                try:
                    # Attempt to reconnect
                    ws = _attempt_websocket_reconnect(
                        ws_url,
                        WEBSOCKET_RECONNECT_ATTEMPTS,
                        WEBSOCKET_RECONNECT_DELAY_S,
                        closed_err,
                    )

                    print(
                        "worker-comfyui - Resuming message listening after successful reconnect."
                    )
                    continue
                except (
                    websocket.WebSocketConnectionClosedException
                ) as reconn_failed_err:
                    # If _attempt_websocket_reconnect fails, it raises this exception
                    # Let this exception propagate to the outer handler's except block
                    raise reconn_failed_err

            except json.JSONDecodeError:
                print(f"worker-comfyui - Received invalid JSON message via websocket.")

        if not execution_done and not errors:
            raise ValueError(
                "Workflow monitoring loop exited without confirmation of completion or error."
            )

        # Fetch history even if there were execution errors, some outputs might exist
        print(f"worker-comfyui - Fetching history for prompt {prompt_id}...")
        history = get_history(prompt_id)

        if prompt_id not in history:
            error_msg = f"Prompt ID {prompt_id} not found in history after execution."
            print(f"worker-comfyui - {error_msg}")
            if not errors:
                return {"error": error_msg}
            else:
                errors.append(error_msg)
                return {
                    "error": "Job processing failed, prompt ID not found in history.",
                    "details": errors,
                }

        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {})

        if not outputs:
            warning_msg = f"No outputs found in history for prompt {prompt_id}."
            print(f"worker-comfyui - {warning_msg}")
            if not errors:
                errors.append(warning_msg)

        print(f"worker-comfyui - Processing {len(outputs)} output nodes...")
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                print(
                    f"worker-comfyui - Node {node_id} contains {len(node_output['images'])} image(s)"
                )
                for image_info in node_output["images"]:
                    filename = image_info.get("filename")
                    subfolder = image_info.get("subfolder", "")
                    img_type = image_info.get("type")

                    # skip temp images
                    if img_type == "temp":
                        print(
                            f"worker-comfyui - Skipping image {filename} because type is 'temp'"
                        )
                        continue

                    if not filename:
                        warn_msg = f"Skipping image in node {node_id} due to missing filename: {image_info}"
                        print(f"worker-comfyui - {warn_msg}")
                        errors.append(warn_msg)
                        continue

                    image_bytes = get_image_data(filename, subfolder, img_type)

                    if image_bytes:
                        file_extension = os.path.splitext(filename)[1] or ".png"

                        # Prefer GCS upload by default; base64 only if requested or no creds
                        if not return_base64 and gcs_bucket_creds and gcs_bucket_name:
                            try:
                                os.makedirs("/runpod-volume/tmp", exist_ok=True)
                                with tempfile.NamedTemporaryFile(dir="/runpod-volume/tmp", suffix=file_extension, delete=False) as temp_file:
                                    temp_file.write(image_bytes)
                                    temp_file_path = temp_file.name
                                print(f"worker-comfyui - Wrote image bytes to temporary file: {temp_file_path}")
                                print(
                                    f"worker-comfyui - Uploading {filename} to bucket {gcs_bucket_name} with prefix '{upload_prefix}'..."
                                )
                                presigned_url = upload_file_to_bucket(
                                    filename,
                                    temp_file_path,
                                    gcs_bucket_creds,
                                    gcs_bucket_name,
                                    upload_prefix,
                                )
                                os.remove(temp_file_path)
                                print(
                                    f"worker-comfyui - Uploaded {filename} to bucket: {presigned_url}"
                                )
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "url",
                                        "data": presigned_url,
                                    }
                                )
                            except Exception as e:
                                error_msg = (
                                    f"Error uploading {filename} to bucket {gcs_bucket_name} "
                                    f"(endpoint={gcs_bucket_creds.get('endpointUrl')}, prefix={upload_prefix}): {e}"
                                )
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                        else:
                            try:
                                base64_image = base64.b64encode(image_bytes).decode(
                                    "utf-8"
                                )
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "base64",
                                        "data": base64_image,
                                    }
                                )
                                print(f"worker-comfyui - Encoded {filename} as base64")
                            except Exception as e:
                                error_msg = f"Error encoding {filename} to base64: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                    else:
                        error_msg = f"Failed to fetch image data for {filename} from /view endpoint."
                        errors.append(error_msg)

            # --- Videos ---
            if "videos" in node_output:
                print(
                    f"worker-comfyui - Node {node_id} contains {len(node_output['videos'])} video(s)"
                )
                for video_info in node_output["videos"]:
                    filename = video_info.get("filename")
                    subfolder = video_info.get("subfolder", "")
                    vid_type = video_info.get("type")

                    # skip temp artifacts
                    if vid_type == "temp":
                        print(
                            f"worker-comfyui - Skipping video {filename} because type is 'temp'"
                        )
                        continue

                    if not filename:
                        warn_msg = f"Skipping video in node {node_id} due to missing filename: {video_info}"
                        print(f"worker-comfyui - {warn_msg}")
                        errors.append(warn_msg)
                        continue

                    # Reuse /view endpoint (works for arbitrary files, not only images)
                    file_bytes = get_image_data(filename, subfolder, vid_type)

                    if file_bytes:
                        file_extension = os.path.splitext(filename)[1] or ".mp4"

                        # Prefer bucket upload; base64 only if explicitly requested or no creds
                        if not return_base64 and gcs_bucket_creds and gcs_bucket_name:
                            try:
                                os.makedirs("/runpod-volume/tmp", exist_ok=True)
                                with tempfile.NamedTemporaryFile(dir="/runpod-volume/tmp", suffix=file_extension, delete=False) as temp_file:
                                    temp_file.write(file_bytes)
                                    temp_file_path = temp_file.name
                                print(f"worker-comfyui - Wrote video bytes to temporary file: {temp_file_path}")
                                print(
                                    f"worker-comfyui - Uploading {filename} to bucket {gcs_bucket_name} with prefix '{upload_prefix}'..."
                                )
                                presigned_url = upload_file_to_bucket(
                                    filename,
                                    temp_file_path,
                                    gcs_bucket_creds,
                                    gcs_bucket_name,
                                    upload_prefix,
                                )
                                os.remove(temp_file_path)
                                print(
                                    f"worker-comfyui - Uploaded {filename} to bucket: {presigned_url}"
                                )
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "url",
                                        "data": presigned_url,
                                    }
                                )
                            except Exception as e:
                                error_msg = (
                                    f"Error uploading {filename} to bucket {gcs_bucket_name} "
                                    f"(endpoint={gcs_bucket_creds.get('endpointUrl')}, prefix={upload_prefix}): {e}"
                                )
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                        else:
                            try:
                                base64_video = base64.b64encode(file_bytes).decode("utf-8")
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "base64",
                                        "data": base64_video,
                                    }
                                )
                                print(f"worker-comfyui - Encoded {filename} as base64 (video)")
                            except Exception as e:
                                error_msg = f"Error encoding {filename} to base64: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                    else:
                        error_msg = f"Failed to fetch video data for {filename} from /view endpoint."
                        errors.append(error_msg)

            # --- GIFs ---
            if "gifs" in node_output:
                print(
                    f"worker-comfyui - Node {node_id} contains {len(node_output['gifs'])} gif(s)"
                )
                for gif_info in node_output["gifs"]:
                    filename = gif_info.get("filename")
                    subfolder = gif_info.get("subfolder", "")
                    gif_type = gif_info.get("type")

                    if gif_type == "temp":
                        print(
                            f"worker-comfyui - Skipping gif {filename} because type is 'temp'"
                        )
                        continue

                    if not filename:
                        warn_msg = f"Skipping gif in node {node_id} due to missing filename: {gif_info}"
                        print(f"worker-comfyui - {warn_msg}")
                        errors.append(warn_msg)
                        continue

                    file_bytes = get_image_data(filename, subfolder, gif_type)

                    if file_bytes:
                        file_extension = os.path.splitext(filename)[1] or ".gif"

                        if not return_base64 and gcs_bucket_creds and gcs_bucket_name:
                            try:
                                os.makedirs("/runpod-volume/tmp", exist_ok=True)
                                with tempfile.NamedTemporaryFile(dir="/runpod-volume/tmp", suffix=file_extension, delete=False) as temp_file:
                                    temp_file.write(file_bytes)
                                    temp_file_path = temp_file.name
                                print(f"worker-comfyui - Wrote gif bytes to temporary file: {temp_file_path}")
                                print(
                                    f"worker-comfyui - Uploading {filename} to bucket {gcs_bucket_name} with prefix '{upload_prefix}'..."
                                )
                                presigned_url = upload_file_to_bucket(
                                    filename,
                                    temp_file_path,
                                    gcs_bucket_creds,
                                    gcs_bucket_name,
                                    upload_prefix,
                                )
                                os.remove(temp_file_path)
                                print(
                                    f"worker-comfyui - Uploaded {filename} to bucket: {presigned_url}"
                                )
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "url",
                                        "data": presigned_url,
                                    }
                                )
                            except Exception as e:
                                error_msg = (
                                    f"Error uploading {filename} to bucket {gcs_bucket_name} "
                                    f"(endpoint={gcs_bucket_creds.get('endpointUrl')}, prefix={upload_prefix}): {e}"
                                )
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                        else:
                            try:
                                base64_gif = base64.b64encode(file_bytes).decode("utf-8")
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "base64",
                                        "data": base64_gif,
                                    }
                                )
                                print(f"worker-comfyui - Encoded {filename} as base64 (gif)")
                            except Exception as e:
                                error_msg = f"Error encoding {filename} to base64: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                    else:
                        error_msg = f"Failed to fetch gif data for {filename} from /view endpoint."
                        errors.append(error_msg)

            # Check for other output types
            other_keys = [k for k in node_output.keys() if k not in ("images", "videos", "gifs")]
            if other_keys:
                warn_msg = (
                    f"Node {node_id} produced unhandled output keys: {other_keys}."
                )
                print(f"worker-comfyui - WARNING: {warn_msg}")
                print(
                    f"worker-comfyui - --> If this output is useful, please consider opening an issue on GitHub to discuss adding support."
                )

    except websocket.WebSocketException as e:
        error_msg = f"WebSocket communication error: {e}"
        print(f"worker-comfyui - WebSocket Error: {error_msg}")
        print(f"worker-comfyui - WebSocket error type: {type(e).__name__}")
        print(f"worker-comfyui - Job ID: {job_id}, Prompt ID: {prompt_id}")
        print(traceback.format_exc())
        return {"error": error_msg}
    except requests.RequestException as e:
        error_msg = f"HTTP communication error with ComfyUI: {e}"
        print(f"worker-comfyui - HTTP Request Error: {error_msg}")
        print(f"worker-comfyui - Request error type: {type(e).__name__}")
        print(f"worker-comfyui - Job ID: {job_id}, Prompt ID: {prompt_id}")
        print(traceback.format_exc())
        return {"error": error_msg}
    except ValueError as e:
        error_msg = str(e)
        print(f"worker-comfyui - Value Error: {error_msg}")
        print(f"worker-comfyui - Job ID: {job_id}, Prompt ID: {prompt_id}")
        print(traceback.format_exc())
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        print(f"worker-comfyui - Unexpected Handler Error: {error_msg}")
        print(f"worker-comfyui - Error type: {type(e).__name__}")
        print(f"worker-comfyui - Job ID: {job_id}, Prompt ID: {prompt_id}")
        print(f"worker-comfyui - Job input summary: {json.dumps({k: str(v)[:100] + '...' if len(str(v)) > 100 else v for k, v in job_input.items()}, indent=2)}")
        print(traceback.format_exc())
        return {"error": error_msg}
    finally:
        if ws and ws.connected:
            print(f"worker-comfyui - Closing websocket connection.")
            ws.close()

    final_result = {}

    if output_data:
        final_result["images"] = output_data

    if errors:
        final_result["errors"] = errors
        print(f"worker-comfyui - Job completed with errors/warnings: {errors}")

    if not output_data and errors:
        print(f"worker-comfyui - Job failed with no output images.")
        return {
            "error": "Job processing failed",
            "details": errors,
        }
    elif not output_data and not errors:
        print(
            f"worker-comfyui - Job completed successfully, but the workflow produced no images."
        )
        final_result["status"] = "success_no_images"
        final_result["images"] = []

    # Логируем время завершения и общее время выполнения
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"worker-comfyui - Job completed at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
    print(f"worker-comfyui - Total execution time: {execution_time:.2f} seconds")
    print(f"worker-comfyui - Job completed. Returning {len(output_data)} image(s).")
    return final_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ComfyUI handler")
    parser.add_argument("--local", action="store_true", help="Run in local test mode (no ComfyUI)")
    parser.add_argument("--image", default=os.environ.get("LOCAL_IMAGE_PATH", "/girs.png"), help="Path to local image for --local mode")
    parser.add_argument("--path", default="", help="Upload path prefix inside bucket (S3 key prefix)")
    parser.add_argument(
        "--return-base64",
        dest="return_base64",
        action="store_true",
        help="Return base64 instead of uploading to bucket",
    )
    parser.add_argument(
        "--as-url",
        dest="return_base64",
        action="store_false",
        help="Upload to bucket and return a pre-signed URL",
    )
    parser.set_defaults(return_base64=False)
    args = parser.parse_args()

    if args.local:
        job = {
            "id": "job-local-test",
            "input": {
                "local": True,
                "local_image_path": args.image,
                "return_base64": args.return_base64,
                "path": args.path,
            },
        }
        result = handler(job)
        print(json.dumps(result, indent=2))
    else:
        print("worker-comfyui - Starting handler...")
        runpod.serverless.start({"handler": handler})
