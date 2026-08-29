"""
models.py — Định nghĩa GraphState và AuditEntry cho Lab 27 HITL.

GraphState  : persistent state truyền qua các node của LangGraph.
AuditEntry  : schema cho audit trail (mỗi quyết định tạo ra một entry).
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# GraphState
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    """State dùng chung xuyên suốt LangGraph workflow.

    Tất cả các node đọc và ghi vào dict này.
    MemorySaver giữ state tồn tại khi graph bị interrupt.
    """

    customer_id: str
    """Định danh khách hàng được đánh giá."""

    proposed_action: str
    """Hành động agent đề xuất (e.g. 'send_email', 'increase_credit_limit')."""

    confidence_score: float
    """Mức độ tự tin của agent, từ 0.0 đến 1.0."""

    reasoning: str
    """Giải thích lý do agent đưa ra đề xuất đó."""

    human_decision: str | None
    """Quyết định của human reviewer: 'approve', 'reject', hoặc 'edit:<action_mới>'."""


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    """Một bản ghi audit trail cho mỗi quyết định quan trọng trong workflow.

    Được serialise ra JSON và append vào audit_log.json.
    """

    timestamp: str = Field(..., description="ISO-8601 timestamp khi entry được tạo.")
    agent_id: str = Field(..., description="Định danh của agent thực hiện đánh giá.")
    action: str = Field(..., description="Hành động cuối cùng được thực thi hoặc huỷ.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score của agent.")
    reviewer_id: str = Field(..., description="ID của human reviewer (hoặc 'auto' nếu tự động).")
    decision: str = Field(..., description="Quyết định: 'approve', 'reject', 'edit', hoặc 'auto_execute'.")
