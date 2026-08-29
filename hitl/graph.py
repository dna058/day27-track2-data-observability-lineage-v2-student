"""
graph.py — LangGraph workflow cho bài toán Churn Risk HITL.

Cấu trúc graph:
    START
      └─> evaluate_customer          (agent reasoning node)
              └─> route_action       (conditional edge)
                    ├─> execute_low_risk_action   (auto-execute path)
                    └─> execute_high_risk_action  (human-review path, interrupt_before)
                              └─> END

Hard policy rules:
    1. increase_credit_limit  → luôn route sang execute_high_risk_action
    2. confidence >= 0.85 + low-risk action → auto-execute
    3. confidence < 0.85 → escalate sang human review

Interrupt:
    interrupt_before=["execute_high_risk_action"] dừng graph TRƯỚC khi
    node đó chạy. MemorySaver giữ toàn bộ state trong lúc chờ reviewer.
"""

from __future__ import annotations

import json
import os
import random
import datetime
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from models import GraphState, AuditEntry

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.json")

# Threshold confidence để auto-execute low-risk action
CONFIDENCE_THRESHOLD = 0.85

# Tập action luôn phải qua human review (hard policy rule)
HIGH_RISK_ACTIONS: set[str] = {"increase_credit_limit"}

# Agent identifier
AGENT_ID = "churn-risk-agent-v1"


# ---------------------------------------------------------------------------
# Dữ liệu mock khách hàng
# ---------------------------------------------------------------------------

MOCK_CUSTOMERS: dict[str, dict] = {
    "CUST001": {
        "name": "Nguyễn Văn A",
        "churn_probability": 0.78,
        "toi": 52_000_000,   # Total Operating Income (VND)
        "months_inactive": 3,
        "credit_limit": 100_000_000,
    },
    "CUST002": {
        "name": "Trần Thị B",
        "churn_probability": 0.35,
        "toi": 18_000_000,
        "months_inactive": 0,
        "credit_limit": 50_000_000,
    },
    "CUST003": {
        "name": "Lê Văn C",
        "churn_probability": 0.91,
        "toi": 120_000_000,
        "months_inactive": 6,
        "credit_limit": 200_000_000,
    },
    "CUST004": {
        "name": "Phạm Thị D",
        "churn_probability": 0.55,
        "toi": 30_000_000,
        "months_inactive": 1,
        "credit_limit": 80_000_000,
    },
}


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

def append_audit_entry(entry: AuditEntry) -> None:
    """Đọc audit_log.json, append entry mới, ghi lại. Thread-safe đủ dùng cho lab."""
    if os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            try:
                records: list[dict] = json.load(f)
            except json.JSONDecodeError:
                records = []
    else:
        records = []

    records.append(entry.model_dump())

    with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Node 1: evaluate_customer  — Agent Reasoning
# ---------------------------------------------------------------------------

def evaluate_customer(state: GraphState) -> GraphState:
    """Agent đánh giá khách hàng và đề xuất action.

    Trong production, đây sẽ gọi một LLM với customer data làm context.
    Ở đây ta dùng mock logic để minh hoạ workflow.

    Returns:
        Partial state update với proposed_action, confidence_score, reasoning.
    """
    customer_id = state["customer_id"]
    customer = MOCK_CUSTOMERS.get(customer_id)

    if customer is None:
        # Fallback nếu không tìm thấy customer trong mock data
        customer = {
            "name": "Unknown",
            "churn_probability": round(random.uniform(0.3, 0.9), 2),
            "toi": random.randint(10_000_000, 150_000_000),
            "months_inactive": random.randint(0, 8),
            "credit_limit": random.randint(30_000_000, 300_000_000),
        }

    churn_prob = customer["churn_probability"]
    toi = customer["toi"]
    months_inactive = customer["months_inactive"]

    # --- Mock agent reasoning logic ---
    # Agent quyết định action và confidence dựa trên các feature

    if churn_prob >= 0.75 and toi >= 50_000_000:
        # High-value customer có nguy cơ rời đi cao → đề xuất tăng hạn mức
        proposed_action = "increase_credit_limit"
        # Confidence cao nhưng hard rule vẫn override
        confidence_score = round(0.90 + random.uniform(-0.05, 0.09), 2)
        confidence_score = min(1.0, max(0.0, confidence_score))
        reasoning = (
            f"Khách hàng {customer_id} có xác suất rời bỏ {churn_prob:.0%} và "
            f"TOI {toi:,} VND. Tăng hạn mức tín dụng có thể cải thiện mức độ "
            f"gắn kết và giảm nguy cơ churn."
        )
    elif churn_prob >= 0.5 or months_inactive >= 3:
        # Nguy cơ trung bình → gửi email giữ chân
        proposed_action = "send_email"
        # Confidence phụ thuộc vào rõ ràng của tín hiệu
        confidence_score = round(0.80 + churn_prob * 0.15 + random.uniform(-0.03, 0.05), 2)
        confidence_score = min(1.0, max(0.0, confidence_score))
        reasoning = (
            f"Khách hàng {customer_id} có xác suất rời bỏ {churn_prob:.0%} "
            f"và không hoạt động {months_inactive} tháng. "
            f"Gửi email retention phù hợp để tái kích hoạt."
        )
    else:
        # Nguy cơ thấp → gửi email thông thường
        proposed_action = "send_email"
        confidence_score = round(0.88 + random.uniform(-0.04, 0.08), 2)
        confidence_score = min(1.0, max(0.0, confidence_score))
        reasoning = (
            f"Khách hàng {customer_id} có xác suất rời bỏ thấp ({churn_prob:.0%}). "
            f"Gửi email chăm sóc định kỳ để duy trì mối quan hệ."
        )

    return {
        **state,
        "proposed_action": proposed_action,
        "confidence_score": confidence_score,
        "reasoning": reasoning,
        "human_decision": None,
    }


# ---------------------------------------------------------------------------
# Node 2a: execute_low_risk_action  — Auto-Execute
# ---------------------------------------------------------------------------

def execute_low_risk_action(state: GraphState) -> GraphState:
    """Thực thi low-risk action tự động (không cần human review).

    Ghi audit entry với reviewer_id='auto' và decision='auto_execute'.
    """
    action = state["proposed_action"]
    confidence = state["confidence_score"]
    customer_id = state["customer_id"]

    print(f"[AUTO-EXECUTE] customer={customer_id} action={action} confidence={confidence:.2f}")

    entry = AuditEntry(
        timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
        agent_id=AGENT_ID,
        action=action,
        confidence=confidence,
        reviewer_id="auto",
        decision="auto_execute",
    )
    append_audit_entry(entry)

    return {**state, "human_decision": "auto_execute"}


# ---------------------------------------------------------------------------
# Node 2b: execute_high_risk_action  — Human Review & Execute/Abort
# ---------------------------------------------------------------------------

def execute_high_risk_action(state: GraphState) -> GraphState:
    """Thực thi hoặc huỷ high-risk action dựa trên quyết định của human reviewer.

    Node này chỉ chạy SAU KHI graph được resume từ interrupt.
    state["human_decision"] đã được cập nhật từ Streamlit UI.
    """
    human_decision = state.get("human_decision") or "reject"
    action = state["proposed_action"]
    confidence = state["confidence_score"]
    customer_id = state["customer_id"]

    # Phân tích decision: có thể là "approve", "reject", hoặc "edit:<action_mới>"
    if human_decision.startswith("edit:"):
        final_action = human_decision.split(":", 1)[1].strip()
        decision_type = "edit"
    else:
        final_action = action
        decision_type = human_decision  # "approve" hoặc "reject"

    if decision_type == "approve":
        print(f"[APPROVED] customer={customer_id} action={final_action} confidence={confidence:.2f}")
    elif decision_type == "edit":
        print(f"[EDITED] customer={customer_id} original={action} → new={final_action}")
    else:
        print(f"[REJECTED] customer={customer_id} action={final_action}")

    # Ghi audit entry
    entry = AuditEntry(
        timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
        agent_id=AGENT_ID,
        action=final_action,
        confidence=confidence,
        reviewer_id="operator_01",  # Trong production lấy từ auth session
        decision=decision_type,
    )
    append_audit_entry(entry)

    return {**state, "proposed_action": final_action}


# ---------------------------------------------------------------------------
# Conditional Edge: route_action
# ---------------------------------------------------------------------------

def route_action(
    state: GraphState,
) -> Literal["execute_high_risk_action", "execute_low_risk_action"]:
    """Quyết định bước tiếp theo dựa trên action và confidence score.

    Thứ tự ưu tiên:
        1. Hard Policy Rule  : action thuộc HIGH_RISK_ACTIONS → human review
        2. Auto-Execute      : confidence >= THRESHOLD + low-risk → tự động
        3. Escalate          : confidence < THRESHOLD → human review
    """
    action = state["proposed_action"]
    confidence = state["confidence_score"]

    # Rule 1 — Policy Override (ưu tiên cao nhất)
    if action in HIGH_RISK_ACTIONS:
        print(
            f"[ROUTE] Policy Override: action='{action}' → execute_high_risk_action "
            f"(confidence={confidence:.2f} bị ignore)"
        )
        return "execute_high_risk_action"

    # Rule 2 — Auto-Execute
    if confidence >= CONFIDENCE_THRESHOLD:
        print(f"[ROUTE] Auto-Execute: action='{action}' confidence={confidence:.2f} → execute_low_risk_action")
        return "execute_low_risk_action"

    # Rule 3 — Escalate
    print(
        f"[ROUTE] Escalate: action='{action}' confidence={confidence:.2f} < {CONFIDENCE_THRESHOLD} "
        f"→ execute_high_risk_action"
    )
    return "execute_high_risk_action"


# ---------------------------------------------------------------------------
# Build & Compile Graph
# ---------------------------------------------------------------------------

def build_graph():
    """Khởi tạo và compile LangGraph workflow với MemorySaver và interrupt_before."""
    builder = StateGraph(GraphState)

    # Thêm các node
    builder.add_node("evaluate_customer", evaluate_customer)
    builder.add_node("execute_low_risk_action", execute_low_risk_action)
    builder.add_node("execute_high_risk_action", execute_high_risk_action)

    # Kết nối edges
    builder.add_edge(START, "evaluate_customer")
    builder.add_conditional_edges(
        "evaluate_customer",
        route_action,
        {
            "execute_low_risk_action": "execute_low_risk_action",
            "execute_high_risk_action": "execute_high_risk_action",
        },
    )
    builder.add_edge("execute_low_risk_action", END)
    builder.add_edge("execute_high_risk_action", END)

    # Compile với MemorySaver (bắt buộc cho interrupt) và interrupt_before
    memory = MemorySaver()
    graph = builder.compile(
        checkpointer=memory,
        interrupt_before=["execute_high_risk_action"],
    )
    return graph


# Singleton graph (import bởi app.py)
churn_graph = build_graph()


# ---------------------------------------------------------------------------
# Quick CLI test (python graph.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    customer_id = sys.argv[1] if len(sys.argv) > 1 else "CUST001"
    thread_id = f"test-{customer_id}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: GraphState = {
        "customer_id": customer_id,
        "proposed_action": "",
        "confidence_score": 0.0,
        "reasoning": "",
        "human_decision": None,
    }

    print(f"\n{'='*60}")
    print(f"Chạy graph cho customer: {customer_id}")
    print(f"{'='*60}")

    # Invoke lần 1 — graph sẽ dừng nếu cần human review
    result = churn_graph.invoke(initial_state, config)

    pending = churn_graph.get_state(config)
    next_nodes = pending.next

    if next_nodes and "execute_high_risk_action" in next_nodes:
        s = pending.values
        print(f"\n[INTERRUPTED] Chờ human review:")
        print(f"  proposed_action : {s['proposed_action']}")
        print(f"  confidence_score: {s['confidence_score']:.2f}")
        print(f"  reasoning       : {s['reasoning']}")

        # Giả lập human approve
        print("\n[SIM] Human quyết định: approve")
        churn_graph.update_state(config, {"human_decision": "approve"})
        churn_graph.invoke(None, config)
        print("[DONE] Graph đã được resume và hoàn thành.")
    else:
        print(f"\n[AUTO-EXECUTED] action={result.get('proposed_action')}")

    print(f"\nAudit log: {AUDIT_LOG_PATH}\n")
