from collections.abc import Generator
import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import settings

logger = logging.getLogger(__name__)


def get_db_connect_args() -> dict[str, str]:
    connect_args: dict[str, str] = {}
    ca_file = settings.resolved_rds_ca_file
    if ca_file:
        ca_path = Path(ca_file)
        if ca_path.is_file():
            connect_args["sslmode"] = settings.aliyun_rds_ssl_mode.strip() or "verify-ca"
            connect_args["sslrootcert"] = str(ca_path)
        else:
            logger.warning(
                "ALIYUN_RDS_CA_FILE=%s does not exist inside runtime; skipping verify-ca. "
                "Copy the CA cert into deploy/certs/ so it mounts at /app/certs/%s if strict verification is needed.",
                ca_file,
                ca_path.name,
            )
            if settings.aliyun_rds_ssl_mode.strip():
                connect_args["sslmode"] = settings.aliyun_rds_ssl_mode.strip()
    elif settings.aliyun_rds_ssl_mode.strip():
        connect_args["sslmode"] = settings.aliyun_rds_ssl_mode.strip()
    return connect_args


engine = create_engine(
    settings.resolved_database_url,
    connect_args=get_db_connect_args(),
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
