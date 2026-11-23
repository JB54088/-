"""Aliyun OSS adapter for archiving original uploaded ABC Excel files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from ...core.config import settings

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")


class OssStorageError(RuntimeError):
    """Raised when uploading or signing an Aliyun OSS object fails."""


@dataclass(frozen=True)
class OssUploadResult:
    bucket: str
    object_key: str
    sha256: str
    size_bytes: int


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sanitize_filename(file_name: str) -> str:
    cleaned = re.sub(r"[\\/\x00-\x1f]+", "_", (file_name or "abc.xlsx").strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[-120:] if len(cleaned) > 120 else (cleaned or "abc.xlsx")


def build_oss_object_key(file_name: str, sha256_hex: str, now: datetime | None = None) -> str:
    current = (now or datetime.now(BUSINESS_TZ)).astimezone(BUSINESS_TZ)
    prefix = (settings.oss_prefix or "abc-imports").strip("/") or "abc-imports"
    safe_name = _sanitize_filename(file_name)
    return f"{prefix}/{current:%Y}/{current:%m}/{current:%Y%m%d_%H%M%S}_{sha256_hex[:12]}_{safe_name}"


def _content_type_for(file_name: str) -> str:
    if (file_name or "").lower().endswith(".xls"):
        return "application/vnd.ms-excel"
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload_excel_to_oss(content: bytes, file_name: str) -> OssUploadResult | None:
    """Upload raw Excel bytes to Aliyun OSS immediately on user upload.

    Returns ``None`` when OSS credentials/bucket are not configured (for example
    in local offline development or unit tests).
    """
    if not settings.oss_enabled:
        return None

    try:
        import oss2
    except ImportError as exc:
        raise OssStorageError("后端缺少 oss2 依赖，请重新构建后端镜像 (pip install oss2)") from exc

    sha256_hex = compute_sha256(content)
    object_key = build_oss_object_key(file_name, sha256_hex)
    bucket_name = settings.oss_bucket_name.strip()
    try:
        auth = oss2.Auth(settings.aliyun_access_key_id.strip(), settings.aliyun_access_key.strip())
        bucket = oss2.Bucket(auth, settings.oss_upload_endpoint, bucket_name)
        result = bucket.put_object(
            object_key,
            content,
            headers={"Content-Type": _content_type_for(file_name)},
        )
        if not (200 <= int(getattr(result, "status", 0)) < 300):
            raise OssStorageError(f"OSS 返回异常状态码: {getattr(result, 'status', 'unknown')}")
    except OssStorageError:
        raise
    except Exception as exc:
        raise OssStorageError(f"上传 Excel 原文件至阿里云 OSS 失败：{exc}") from exc

    return OssUploadResult(
        bucket=bucket_name,
        object_key=object_key,
        sha256=sha256_hex,
        size_bytes=len(content),
    )


def generate_excel_download_url(
    object_key: str,
    download_filename: str,
    *,
    bucket_name: str | None = None,
    expires_in: int | None = None,
) -> str:
    """Generate a short-lived signed HTTPS download URL using the public OSS endpoint."""
    if not settings.oss_enabled:
        raise OssStorageError("当前环境未配置阿里云 OSS，无法生成原文件下载链接")

    try:
        import oss2
    except ImportError as exc:
        raise OssStorageError("后端缺少 oss2 依赖，请重新构建后端镜像 (pip install oss2)") from exc

    target_bucket = (bucket_name or settings.oss_bucket_name).strip()
    ttl = expires_in or settings.oss_url_expire_seconds
    ext = ".xls" if (download_filename or "").lower().endswith(".xls") else ".xlsx"
    disposition = f"attachment; filename=\"abc_import{ext}\"; filename*=UTF-8''{quote(download_filename or f'abc_import{ext}')}"
    try:
        auth = oss2.Auth(settings.aliyun_access_key_id.strip(), settings.aliyun_access_key.strip())
        # Always sign browser download links against the public endpoint so the
        # administrator's browser can download directly even when ECS uploads internally.
        bucket = oss2.Bucket(auth, settings.oss_public_endpoint, target_bucket)
        return bucket.sign_url(
            "GET",
            object_key,
            ttl,
            slash_safe=True,
            params={"response-content-disposition": disposition},
        )
    except Exception as exc:
        raise OssStorageError(f"生成 OSS 下载签名链接失败：{exc}") from exc
