"""Pydantic request/response schemas organized by domain and re-exported uniformly."""

from .agent import (
    AgentQueryRequest,
    AgentQueryResponse,
    ChartPayload,
    ChartPoint,
    GroupBy,
    Metric,
    QueryFilters,
    QueryPlan,
    TimeRange,
    TimeRangeType,
)
from .auth import DepartmentBrief, LoginRequest, TokenResponse, UserBrief, UserProfileUpdate
from .common import LeadStatus, PoolMatchStatus, SourceCategory, SourceLevel1, SourceLevel2
from .customer import (
    AssignmentRequest,
    BulkAssignmentRequest,
    CustomerDetail,
    CustomerDetailResponse,
    CustomerListItem,
    CustomerVoidRequest,
    PoolManualMatchRequest,
    PoolMatchCandidateResponse,
    ReassignRequest,
    TimelineEvent,
)
from .excel_import import ExcelImportBindRequest, ExcelImportIgnoreRequest
from .lead import DuplicateLeadReviewRequest, LeadCreate, LeadListItem, LeadReviewRequest
from .order import CustomerBalanceTransactionResponse, OrderItemResponse, OrderResponse
from .report import ReportResponse
from .tag import CustomerTagsRequest, TagCreate, TagResponse, TagUpdate

__all__ = [
    "AgentQueryRequest",
    "AgentQueryResponse",
    "AssignmentRequest",
    "BulkAssignmentRequest",
    "ChartPayload",
    "ChartPoint",
    "CustomerBalanceTransactionResponse",
    "CustomerDetail",
    "CustomerDetailResponse",
    "CustomerListItem",
    "CustomerTagsRequest",
    "CustomerVoidRequest",
    "DepartmentBrief",
    "DuplicateLeadReviewRequest",
    "ExcelImportBindRequest",
    "ExcelImportIgnoreRequest",
    "GroupBy",
    "LeadCreate",
    "LeadListItem",
    "LeadReviewRequest",
    "LeadStatus",
    "LoginRequest",
    "Metric",
    "OrderItemResponse",
    "OrderResponse",
    "PoolManualMatchRequest",
    "PoolMatchCandidateResponse",
    "PoolMatchStatus",
    "QueryFilters",
    "QueryPlan",
    "ReassignRequest",
    "ReportResponse",
    "SourceCategory",
    "SourceLevel1",
    "SourceLevel2",
    "TagCreate",
    "TagResponse",
    "TagUpdate",
    "TimeRange",
    "TimeRangeType",
    "TimelineEvent",
    "TokenResponse",
    "UserBrief",
    "UserProfileUpdate",
]
