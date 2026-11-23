from fastapi import APIRouter

from .endpoints import (
    auth,
    business_analysis,
    customers,
    dashboard,
    duplicate_reports,
    excel_imports,
    leads,
    orders,
    reports,
    tags,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(leads.router)
api_router.include_router(duplicate_reports.router)
api_router.include_router(customers.router)
api_router.include_router(tags.router)
api_router.include_router(orders.router)
api_router.include_router(reports.router)
api_router.include_router(excel_imports.router)
api_router.include_router(users.router)
api_router.include_router(business_analysis.router)
