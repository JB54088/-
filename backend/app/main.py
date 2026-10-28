import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .database import SessionLocal, engine
from . import models  # noqa: F401
from .routers import auth, customers, dashboard, duplicate_reports, excel_imports, leads, orders, reports, tags, users
from .agents import business_analysis
from .seed import ensure_system_data

app = FastAPI(title="企业客户资产经营平台 API", version="1.0.0", description="企业客户、消费、归属和经营分析 REST API")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(duplicate_reports.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(excel_imports.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(business_analysis.router, prefix="/api")


@app.on_event("startup")
def startup() -> None:
    for _ in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except Exception:
            time.sleep(1)
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    existing_tables = set(inspect(engine).get_table_names())
    if not existing_tables:
        # The initial migration creates the current metadata, while historical
        # follow-up migrations assume legacy columns that do not exist on a
        # brand-new database. Bootstrap the current schema once, then mark the
        # migration history at head. Existing databases still use normal
        # incremental Alembic upgrades below.
        Base.metadata.create_all(bind=engine)
        command.stamp(alembic_config, "head")
    else:
        command.upgrade(alembic_config, "head")
    # Startup may ensure system accounts/config, but must never create demo
    # customers, orders, reports, or import records.
    with SessionLocal() as db:
        ensure_system_data(db)


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok", "service": "customer-assets-api"}
