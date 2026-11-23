from pathlib import Path
from urllib.parse import quote, quote_plus

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_LOCAL_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/customer_assets"


def _normalize_pg_scheme(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    database_url: str = DEFAULT_LOCAL_DB_URL
    jwt_secret_key: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    initial_admin01_password: str = "Admin01@123"
    initial_admin02_password: str = "Admin02@123"
    initial_sales01_password: str = "Sales01@123"
    initial_sales02_password: str = "Sales02@123"
    initial_sales03_password: str = "Sales03@123"
    excel_max_file_size_mb: int = 20
    excel_max_rows: int = 50000

    # Aliyun ECS & RDS PostgreSQL configuration
    aliyun_ecs_addr: str = ""
    aliyun_rds_url: str = ""
    aliyun_rds_port: int = 5432
    aliyun_rds_db_name: str = ""
    aliyun_rds_username: str = ""
    aliyun_rds_pwd: str = ""
    aliyun_rds_ca_file: str = ""
    aliyun_rds_ssl_mode: str = ""

    # Aliyun OSS configuration (stores original uploaded ABC Excel files)
    oss_bucket_name: str = ""
    aliyun_access_key_id: str = Field(
        default="",
        validation_alias=AliasChoices("ALIYUN_ACCESS_KEY_ID", "OSS_ACCESS_KEY_ID"),
    )
    aliyun_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("ALIYUN_ACCESS_KEY", "ALIYUN_ACCESS_KEY_SECRET", "OSS_ACCESS_KEY_SECRET"),
    )
    aliyun_oss_region: str = Field(
        default="oss-cn-beijing",
        validation_alias=AliasChoices("ALIYUN_OSS_REGION", "OSS_REGION"),
    )
    oss_endpoint: str = ""
    oss_internal: bool = False
    oss_prefix: str = "abc-imports"
    oss_url_expire_seconds: int = 600

    # Retained only as deprecated configuration for recovering the old adapter;
    # the running application no longer reads from a data-pool service.
    data_pool_url: str = ""
    data_pool_api_key: str = ""
    data_pool_timeout_seconds: int = 30
    data_pool_customers_path: str = "/customers"
    data_pool_orders_path: str = "/orders"
    ai_provider: str = "mock"
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = "business-analysis-mock"
    ai_mock_mode: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [value.strip() for value in self.cors_origins.split(",") if value.strip()]
        ecs_addr = self.aliyun_ecs_addr.strip()
        if ecs_addr:
            for candidate in (
                ecs_addr if ecs_addr.startswith(("http://", "https://")) else f"http://{ecs_addr}",
                f"https://{ecs_addr}" if not ecs_addr.startswith(("http://", "https://")) else "",
            ):
                if candidate and candidate not in origins:
                    origins.append(candidate)
        return origins

    @property
    def resolved_database_url(self) -> str:
        raw_db_url = (self.database_url or "").strip()
        is_local_placeholder = (not raw_db_url) or any(
            marker in raw_db_url for marker in ("@localhost:", "@127.0.0.1:", "@db:")
        )
        if raw_db_url and not is_local_placeholder:
            return _normalize_pg_scheme(raw_db_url)

        rds_host = self.aliyun_rds_url.strip()
        if rds_host and self.aliyun_rds_username.strip() and self.aliyun_rds_db_name.strip():
            if rds_host.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://")):
                return _normalize_pg_scheme(rds_host)
            for prefix in ("https://", "http://", "tcp://"):
                if rds_host.startswith(prefix):
                    rds_host = rds_host[len(prefix) :]
            rds_host = rds_host.rstrip("/")
            port = self.aliyun_rds_port or 5432
            if ":" in rds_host:
                host_part, port_part = rds_host.rsplit(":", 1)
                if port_part.isdigit():
                    rds_host = host_part
                    port = int(port_part)
            username = quote_plus(self.aliyun_rds_username.strip())
            password = quote_plus(self.aliyun_rds_pwd)
            db_name = quote(self.aliyun_rds_db_name.strip(), safe="")
            return f"postgresql+psycopg2://{username}:{password}@{rds_host}:{port}/{db_name}"

        return _normalize_pg_scheme(raw_db_url or DEFAULT_LOCAL_DB_URL)

    @property
    def resolved_rds_ca_file(self) -> str | None:
        raw = self.aliyun_rds_ca_file.strip()
        if not raw:
            return None
        direct = Path(raw)
        if direct.is_file():
            return str(direct)
        mounted = Path("/app/certs") / direct.name
        if mounted.is_file():
            return str(mounted)
        return raw

    @property
    def oss_enabled(self) -> bool:
        return bool(
            self.oss_bucket_name.strip()
            and self.aliyun_access_key_id.strip()
            and self.aliyun_access_key.strip()
        )

    @property
    def normalized_oss_region(self) -> str:
        region = (self.aliyun_oss_region or "oss-cn-beijing").strip().lower()
        for prefix in ("https://", "http://"):
            if region.startswith(prefix):
                region = region[len(prefix) :]
        if region.endswith(".aliyuncs.com"):
            region = region[: -len(".aliyuncs.com")]
        if region.endswith("-internal"):
            region = region[: -len("-internal")]
        if not region.startswith("oss-"):
            region = f"oss-{region}"
        return region

    @property
    def oss_public_endpoint(self) -> str:
        return f"https://{self.normalized_oss_region}.aliyuncs.com"

    @property
    def oss_upload_endpoint(self) -> str:
        explicit = self.oss_endpoint.strip()
        if explicit:
            return explicit if explicit.startswith(("http://", "https://")) else f"https://{explicit}"
        if self.oss_internal:
            return f"https://{self.normalized_oss_region}-internal.aliyuncs.com"
        return self.oss_public_endpoint


settings = Settings()
