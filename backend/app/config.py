from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/customer_assets"
    jwt_secret_key: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    excel_max_file_size_mb: int = 20
    excel_max_rows: int = 50000
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
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


settings = Settings()
