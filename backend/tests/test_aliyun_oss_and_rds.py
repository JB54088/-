"""Unit tests for Aliyun RDS URL assembly and Aliyun OSS upload/download signing."""

from datetime import datetime
import sys
import types
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.integrations.oss import (
    build_oss_object_key,
    generate_excel_download_url,
    upload_excel_to_oss,
)


class AliyunConfigAndOssTest(unittest.TestCase):
    def test_rds_fields_override_local_db_placeholder_and_encode_password(self):
        cfg = Settings(
            _env_file=None,
            database_url="postgresql+psycopg2://postgres:postgres@db:5432/customer_assets",
            aliyun_rds_url="pgm-2ze123456.pg.rds.aliyuncs.com",
            aliyun_rds_port=5432,
            aliyun_rds_db_name="customer_assets",
            aliyun_rds_username="rds_admin",
            aliyun_rds_pwd="P@ss#w0rd%2026!",
        )
        self.assertEqual(
            cfg.resolved_database_url,
            "postgresql+psycopg2://rds_admin:P%40ss%23w0rd%252026%21@pgm-2ze123456.pg.rds.aliyuncs.com:5432/customer_assets",
        )

    def test_explicit_remote_database_url_is_preserved(self):
        explicit = "postgresql+psycopg2://u:p@custom-rds.internal:5432/prod_db"
        cfg = Settings(
            _env_file=None,
            database_url=explicit,
            aliyun_rds_url="other.pg.rds.aliyuncs.com",
            aliyun_rds_username="u2",
            aliyun_rds_db_name="d2",
        )
        self.assertEqual(cfg.resolved_database_url, explicit)

    def test_oss_endpoints_support_beijing_region_and_internal_mode(self):
        cfg = Settings(
            _env_file=None,
            oss_bucket_name="guanyunchun-excel",
            ALIYUN_ACCESS_KEY_ID="LTAI_TEST",
            ALIYUN_ACCESS_KEY="SECRET_TEST",
            ALIYUN_OSS_REGION="oss-cn-beijing",
            oss_internal=True,
        )
        self.assertTrue(cfg.oss_enabled)
        self.assertEqual(cfg.oss_upload_endpoint, "https://oss-cn-beijing-internal.aliyuncs.com")
        self.assertEqual(cfg.oss_public_endpoint, "https://oss-cn-beijing.aliyuncs.com")

    def test_upload_and_presigned_download_url_with_mock_oss2(self):
        calls: dict[str, object] = {}

        class FakePutResult:
            status = 200

        class FakeBucket:
            def __init__(self, auth, endpoint, bucket_name):
                calls.setdefault("buckets", []).append((endpoint, bucket_name))

            def put_object(self, key, content, headers=None):
                calls["put"] = (key, content, headers)
                return FakePutResult()

            def sign_url(self, method, key, expires, slash_safe=False, params=None):
                calls["sign"] = (method, key, expires, slash_safe, params)
                return f"https://guanyunchun-excel.oss-cn-beijing.aliyuncs.com/{key}?signed=1"

        fake_oss2 = types.SimpleNamespace(
            Auth=lambda ak, sk: (ak, sk),
            Bucket=FakeBucket,
        )

        test_settings = Settings(
            _env_file=None,
            oss_bucket_name="guanyunchun-excel",
            ALIYUN_ACCESS_KEY_ID="LTAI_TEST",
            ALIYUN_ACCESS_KEY="SECRET_TEST",
            ALIYUN_OSS_REGION="oss-cn-beijing",
            oss_internal=True,
        )

        with patch.dict(sys.modules, {"oss2": fake_oss2}), patch("app.integrations.oss.client.settings", test_settings):
            result = upload_excel_to_oss(b"excel-bytes", "收费明细 11月.xlsx")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.bucket, "guanyunchun-excel")
            self.assertTrue(result.object_key.startswith("abc-imports/"))
            self.assertTrue(result.object_key.endswith("_收费明细_11月.xlsx"))

            url = generate_excel_download_url(result.object_key, "收费明细 11月.xlsx")
            self.assertIn("https://guanyunchun-excel.oss-cn-beijing.aliyuncs.com/", url)

        bucket_calls = calls["buckets"]
        self.assertEqual(
            bucket_calls,
            [
                ("https://oss-cn-beijing-internal.aliyuncs.com", "guanyunchun-excel"),
                ("https://oss-cn-beijing.aliyuncs.com", "guanyunchun-excel"),
            ],
        )

    def test_object_key_uses_beijing_calendar_partition(self):
        ts = datetime(2026, 11, 23, 15, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        key = build_oss_object_key("导出明细.xls", "abcdef1234567890", now=ts)
        self.assertEqual(key, "abc-imports/2026/11/20261123_151000_abcdef123456_导出明细.xls")


if __name__ == "__main__":
    unittest.main()
