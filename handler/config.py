import os
import json
from typing import Optional, Dict, Any


DEFAULT_S3_PREFIX = "rp"
DEFAULT_KEYS_PATH = os.environ.get(
    "S3_KEYS_FILE", "keys/lia-profiler-a9ca6352420d.json"
)


def load_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    try:
        if path and os.path.exists(path) and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return None
    return None


def get_s3_config(request_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve S3 configuration from, in order of priority:
    - explicit request-provided credentials (input.s3)
    - JSON file at keys/lia-profiler-a9ca6352420d.json (or S3_KEYS_FILE env)
    - environment variables (S3_* or BUCKET_*)

    Returns a dict with keys: endpoint_url, access_key, secret_key, bucket, region(optional)
    Missing values are left as None.
    """
    cfg: Dict[str, Any] = {
        "endpoint_url": None,
        "access_key": None,
        "secret_key": None,
        "bucket": None,
        "region": None,
    }

    # 1) from request
    req_s3 = request_input.get("s3") if isinstance(request_input, dict) else None
    if isinstance(req_s3, dict):
        cfg["endpoint_url"] = req_s3.get("endpoint") or req_s3.get("endpoint_url")
        cfg["access_key"] = req_s3.get("accessKeyId") or req_s3.get("access_key")
        cfg["secret_key"] = req_s3.get("secretAccessKey") or req_s3.get("secret_key")
        cfg["bucket"] = req_s3.get("bucket")
        cfg["region"] = req_s3.get("region")

    # 2) from JSON file
    if not all([cfg["endpoint_url"], cfg["access_key"], cfg["secret_key"]]):
        json_path = request_input.get("s3_keys_file") or DEFAULT_KEYS_PATH
        json_cfg = load_json_if_exists(json_path)
        if isinstance(json_cfg, dict):
            cfg["endpoint_url"] = cfg["endpoint_url"] or json_cfg.get("endpoint") or json_cfg.get("endpoint_url")
            cfg["access_key"] = cfg["access_key"] or json_cfg.get("accessKeyId") or json_cfg.get("access_key")
            cfg["secret_key"] = cfg["secret_key"] or json_cfg.get("secretAccessKey") or json_cfg.get("secret_key")
            cfg["bucket"] = cfg["bucket"] or json_cfg.get("bucket")
            cfg["region"] = cfg["region"] or json_cfg.get("region")

    # 3) from environment
    env_endpoint = os.environ.get("S3_ENDPOINT_URL") or os.environ.get("BUCKET_ENDPOINT_URL")
    env_access = os.environ.get("S3_ACCESS_KEY") or os.environ.get("AWS_ACCESS_KEY_ID")
    env_secret = os.environ.get("S3_SECRET_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    env_bucket = os.environ.get("S3_BUCKET") or os.environ.get("BUCKET_NAME")
    env_region = os.environ.get("S3_REGION") or os.environ.get("AWS_DEFAULT_REGION")

    cfg["endpoint_url"] = cfg["endpoint_url"] or env_endpoint
    cfg["access_key"] = cfg["access_key"] or env_access
    cfg["secret_key"] = cfg["secret_key"] or env_secret
    cfg["bucket"] = cfg["bucket"] or env_bucket
    cfg["region"] = cfg["region"] or env_region

    return cfg


def resolve_output_prefs(request_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determine how results should be returned.
    Default: upload to S3, do NOT return base64.
    Allow flags: input.return_base64 (bool) OR input.return_base46 (compat spelling).
    """
    ret64 = False
    if isinstance(request_input, dict):
        if isinstance(request_input.get("return_base64"), bool):
            ret64 = request_input["return_base64"]
        # accept misspelling 'base46' as a synonym
        if isinstance(request_input.get("return_base46"), bool):
            ret64 = request_input["return_base46"]

    return {
        "return_base64": ret64,
        "default_prefix": request_input.get("prefix") or DEFAULT_S3_PREFIX,
        "path_from_request": request_input.get("path") or request_input.get("dir") or request_input.get("subpath") or None,
    }


