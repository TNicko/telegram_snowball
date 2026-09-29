"""Remote image refs stored as https:// or s3:// instead of a local file."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import quote

REMOTE_PREFIXES = ("http://", "https://", "s3://")


def is_remote_image_ref(path: str | None) -> bool:
    value = str(path or "").strip()
    return value.startswith(REMOTE_PREFIXES)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    raw = uri.strip()
    if not raw.startswith("s3://"):
        raise ValueError(f"not an s3 uri: {uri}")
    rest = raw[5:]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid s3 uri: {uri}")
    return bucket, key


def presign_s3_get(
    uri: str,
    *,
    expires: int = 3600,
    region: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
) -> str:
    """SigV4 query-string GET for s3:// catalog images that are not stored locally."""
    bucket, key = parse_s3_uri(uri)
    access = (access_key or os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
    secret = (secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip()
    region = (region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-2").strip()
    if not access or not secret:
        raise RuntimeError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required to sign s3:// image URLs.")
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    credential_scope = f"{datestamp}/{region}/s3/aws4_request"
    credential = f"{access}/{credential_scope}"
    host = f"{bucket}.s3.{region}.amazonaws.com"
    canonical_uri = "/" + quote(key, safe="/")
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": credential,
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(int(expires)),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(query.items()))
    canonical_request = "\n".join(
        [
            "GET",
            canonical_uri,
            canonical_query,
            f"host:{host}",
            "",
            "host",
            "UNSIGNED-PAYLOAD",
        ]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    signing_key = _sigv4_key(secret, datestamp, region, "s3")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"


def resolve_remote_image_url(path: str) -> str:
    value = str(path).strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("s3://"):
        return presign_s3_get(value)
    raise ValueError(f"not a remote image ref: {path}")


def _sigv4_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    date_key = _sign(("AWS4" + secret).encode(), datestamp)
    region_key = _sign(date_key, region)
    service_key = _sign(region_key, service)
    return _sign(service_key, "aws4_request")
