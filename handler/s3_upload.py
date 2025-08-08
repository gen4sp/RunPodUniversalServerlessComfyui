import os
from typing import Optional


def build_object_key(prefix: str, path_from_request: Optional[str], filename: str) -> str:
    # Normalize components, ensure no leading slashes inside the key
    safe_parts = [part.strip("/") for part in [prefix, path_from_request, filename] if part]
    # Default to '/rp' root in the URL sense, but S3 key should not start with '/'
    return "/".join(safe_parts)


def upload_via_runpod_helper(job_id: str, file_path: str) -> str:
    """
    Backward-compat: use runpod.serverless.utils.rp_upload helper if endpoint is configured via env.
    Returns HTTPS URL to the uploaded object.
    """
    from runpod.serverless.utils import rp_upload

    return rp_upload.upload_image(job_id, file_path)


def init_boto3_client(s3_cfg: dict):
    import boto3

    session = boto3.session.Session(
        aws_access_key_id=s3_cfg.get("access_key"),
        aws_secret_access_key=s3_cfg.get("secret_key"),
        region_name=s3_cfg.get("region"),
    )
    client = session.client(
        "s3",
        endpoint_url=s3_cfg.get("endpoint_url"),
    )
    return client


def upload_file_to_s3(s3_cfg: dict, bucket: str, object_key: str, file_path: str) -> str:
    """
    Upload using boto3. Returns a URL string (signed or path-based depending on endpoint).
    """
    client = init_boto3_client(s3_cfg)
    extra_args = {}
    # Content-Type best-effort
    if file_path.lower().endswith(".png"):
        extra_args["ContentType"] = "image/png"
    elif file_path.lower().endswith(".jpg") or file_path.lower().endswith(".jpeg"):
        extra_args["ContentType"] = "image/jpeg"

    client.upload_file(file_path, bucket, object_key, ExtraArgs=extra_args or None)

    endpoint = s3_cfg.get("endpoint_url") or ""
    # Try to build a standard URL; for S3-compatible endpoints this often works:
    # https://endpoint/bucket/object_key
    endpoint_no_trailing = endpoint.rstrip("/")
    return f"{endpoint_no_trailing}/{bucket}/{object_key}"


