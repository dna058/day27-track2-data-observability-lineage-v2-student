"""
app.py — Streamlit Human Approval Interface cho Lab 27 HITL.

Chạy:
    cd hitl
    streamlit run app.py

Luồng:
    1. Chọn Customer ID và bấm "Run Agent"
    2. Agent đánh giá và đề xuất action
    3. Nếu cần human review → hiển thị Action Card với 3 nút:
        Approve | Reject | Edit
    4. Sau khi quyết định → graph được resume, audit log được ghi
    5. Hiển thị Audit Trail Table
"""

from __future__ import annotations

import json
import os
import sys

import streamlit as st

# Đảm bảo import từ cùng thư mục
sys.path.insert(0, os.path.dirname(__file__))

from graph import churn_graph, MOCK_CUSTOMERS, AUDIT_LOG_PATH, CONFIDENCE_THRESHOLD
from models import GraphState

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Churn Risk HITL — Lab 27",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Main background */
    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
        min-height: 100vh;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: rgba(255,255,255,0.05);
        border-right: 1px solid rgba(255,255,255,0.1);
    }

    /* Action Card */
    .action-card {
        background: rgba(255, 255, 255, 0.07);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 16px;
        padding: 28px 32px;
        backdrop-filter: blur(12px);
        margin-bottom: 24px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }

    .action-card h3 {
        color: #a78bfa;
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 4px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    .action-card .value {
        color: #f1f5f9;
        font-size: 1.05rem;
        font-weight: 500;
    }

    /* Status badges */
    .badge-high-risk {
        background: linear-gradient(90deg, #ef4444, #dc2626);
        color: white;
        padding: 4px 14px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.06em;
    }

    .badge-low-risk {
        background: linear-gradient(90deg, #10b981, #059669);
        color: white;
        padding: 4px 14px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.06em;
    }

    .badge-auto {
        background: linear-gradient(90deg, #3b82f6, #2563eb);
        color: white;
        padding: 4px 14px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.06em;
    }

    /* Confidence bar */
    .conf-bar-bg {
        background: rgba(255,255,255,0.1);
        border-radius: 9999px;
        height: 10px;
        margin-top: 6px;
    }

    /* Section titles */
    .section-title {
        color: #c4b5fd;
        font-size: 1.4rem;
        font-weight: 700;
        margin-bottom: 16px;
        border-bottom: 1px solid rgba(196,181,253,0.3);
        padding-bottom: 8px;
    }

    /* Result box */
    .result-box {
        border-radius: 12px;
        padding: 20px 24px;
        margin-top: 16px;
        font-size: 1rem;
        font-weight: 500;
    }

    .result-approve {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid #10b981;
        color: #6ee7b7;
    }

    .result-reject {
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid #ef4444;
        color: #fca5a5;
    }

    .result-edit {
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid #f59e0b;
        color: #fde68a;
    }

    .result-auto {
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid #3b82f6;
        color: #93c5fd;
    }

    /* Audit table */
    .audit-table {
        width: 100%;
        border-collapse: collapse;
        color: #e2e8f0;
        font-size: 0.9rem;
    }
    .audit-table th {
        background: rgba(139, 92, 246, 0.3);
        padding: 10px 14px;
        text-align: left;
        font-weight: 600;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .audit-table td {
        padding: 10px 14px;
        border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    .audit-table tr:hover td {
        background: rgba(255,255,255,0.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session State init
# ---------------------------------------------------------------------------

if "graph" not in st.session_state:
    st.session_state["graph"] = churn_graph

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = None

if "pending" not in st.session_state:
    st.session_state["pending"] = False

if "last_result" not in st.session_state:
    st.session_state["last_result"] = None  # dict mô tả kết quả cuối

if "graph_state" not in st.session_state:
    st.session_state["graph_state"] = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🏦 HITL Control Panel")
    st.markdown("---")

    st.markdown("### Chọn khách hàng")
    customer_options = list(MOCK_CUSTOMERS.keys()) + ["CUST_RANDOM"]
    selected_customer = st.selectbox(
        "Customer ID",
        customer_options,
        help="Chọn khách hàng để agent đánh giá.",
    )

    if selected_customer in MOCK_CUSTOMERS:
        c = MOCK_CUSTOMERS[selected_customer]
        st.markdown(
            f"""
            **{c['name']}**  
            Churn Prob: `{c['churn_probability']:.0%}`  
            TOI: `{c['toi']:,} VND`  
            Inactive: `{c['months_inactive']} tháng`  
            Credit Limit: `{c['credit_limit']:,} VND`
            """
        )

    st.markdown("---")
    st.markdown(f"**Confidence Threshold:** `{CONFIDENCE_THRESHOLD}`")
    st.markdown("**Hard Rule:** `increase_credit_limit` → luôn human review")
    st.markdown("---")

    run_btn = st.button("▶ Run Agent", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style='text-align:center; padding: 32px 0 24px 0;'>
        <h1 style='color:#a78bfa; font-size:2.4rem; font-weight:800; letter-spacing:-0.02em; margin:0;'>
            🤖 Churn Risk Agent
        </h1>
        <p style='color:#94a3b8; font-size:1.05rem; margin-top:8px;'>
            Human-in-the-Loop Workflow · Lab 27
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_main, col_audit = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------------------
# Main column
# ---------------------------------------------------------------------------

with col_main:
    # --- Run Agent ---
    if run_btn:
        thread_id = f"session-{selected_customer}-{id(st.session_state)}"
        st.session_state["thread_id"] = thread_id
        st.session_state["pending"] = False
        st.session_state["last_result"] = None

        config = {"configurable": {"thread_id": thread_id}}
        initial_state: GraphState = {
            "customer_id": selected_customer,
            "proposed_action": "",
            "confidence_score": 0.0,
            "reasoning": "",
            "human_decision": None,
        }

        with st.spinner("⚙️ Agent đang đánh giá khách hàng..."):
            st.session_state["graph"].invoke(initial_state, config)

        pending_state = st.session_state["graph"].get_state(config)
        st.session_state["graph_state"] = pending_state.values

        if pending_state.next and "execute_high_risk_action" in pending_state.next:
            st.session_state["pending"] = True
        else:
            st.session_state["pending"] = False
            st.session_state["last_result"] = {
                "type": "auto",
                "action": pending_state.values.get("proposed_action", ""),
                "confidence": pending_state.values.get("confidence_score", 0.0),
            }

    # --- Show pending review card ---
    if st.session_state["pending"] and st.session_state["graph_state"]:
        gs = st.session_state["graph_state"]
        action = gs.get("proposed_action", "")
        confidence = gs.get("confidence_score", 0.0)
        reasoning = gs.get("reasoning", "")
        customer_id = gs.get("customer_id", "")

        # Xác định badge
        is_hard_risk = action == "increase_credit_limit"
        badge_html = (
            '<span class="badge-high-risk">⚠ HIGH RISK — Hard Policy</span>'
            if is_hard_risk
            else '<span class="badge-high-risk">⚠ LOW CONFIDENCE — Escalated</span>'
        )

        # Confidence bar màu
        conf_pct = int(confidence * 100)
        conf_color = "#ef4444" if confidence < 0.7 else "#f59e0b" if confidence < CONFIDENCE_THRESHOLD else "#10b981"

        st.markdown('<div class="section-title">📋 Pending Review</div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="action-card">
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;'>
                    <div>
                        <h3>Customer ID</h3>
                        <div class="value" style="font-size:1.3rem;">{customer_id}</div>
                    </div>
                    {badge_html}
                </div>

                <div style='display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px;'>
                    <div>
                        <h3>Proposed Action</h3>
                        <div class="value" style="color:#f59e0b; font-size:1.15rem;">
                            🎯 {action.replace('_', ' ').title()}
                        </div>
                    </div>
                    <div>
                        <h3>Confidence Score</h3>
                        <div class="value" style="color:{conf_color}; font-size:1.5rem; font-weight:700;">
                            {confidence:.2%}
                        </div>
                        <div class="conf-bar-bg">
                            <div style="width:{conf_pct}%; height:10px; border-radius:9999px;
                                        background:{conf_color}; transition:width 0.4s;"></div>
                        </div>
                    </div>
                </div>

                <div>
                    <h3>Agent Reasoning</h3>
                    <div class="value" style="color:#cbd5e1; font-size:0.95rem; line-height:1.6;">
                        {reasoning}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --- Decision buttons ---
        st.markdown("### 🧑‍⚖️ Human Decision")
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            approve_btn = st.button(
                "✅ Approve",
                type="primary",
                use_container_width=True,
                key="btn_approve",
            )
        with btn_col2:
            reject_btn = st.button(
                "❌ Reject",
                use_container_width=True,
                key="btn_reject",
            )
        with btn_col3:
            edit_btn = st.button(
                "✏️ Edit",
                use_container_width=True,
                key="btn_edit",
            )

        # Edit input (hiện khi bấm Edit)
        if "show_edit" not in st.session_state:
            st.session_state["show_edit"] = False
        if edit_btn:
            st.session_state["show_edit"] = True

        edited_action = None
        if st.session_state.get("show_edit"):
            st.markdown("**Sửa proposed action:**")
            edited_action = st.text_input(
                "New action",
                value=action,
                key="edit_input",
                help="Ví dụ: increase_credit_limit_20M hoặc send_email_vip",
            )
            confirm_edit = st.button("✅ Confirm Edit", type="primary", key="btn_confirm_edit")

            if confirm_edit and edited_action:
                decision = f"edit:{edited_action}"
                config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
                st.session_state["graph"].update_state(config, {"human_decision": decision})
                with st.spinner("▶ Resuming graph..."):
                    st.session_state["graph"].invoke(None, config)
                st.session_state["pending"] = False
                st.session_state["show_edit"] = False
                st.session_state["last_result"] = {
                    "type": "edit",
                    "original": action,
                    "action": edited_action,
                    "confidence": confidence,
                }
                st.rerun()

        # Approve
        if approve_btn:
            config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
            st.session_state["graph"].update_state(config, {"human_decision": "approve"})
            with st.spinner("▶ Resuming graph..."):
                st.session_state["graph"].invoke(None, config)
            st.session_state["pending"] = False
            st.session_state["show_edit"] = False
            st.session_state["last_result"] = {
                "type": "approve",
                "action": action,
                "confidence": confidence,
            }
            st.rerun()

        # Reject
        if reject_btn:
            config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
            st.session_state["graph"].update_state(config, {"human_decision": "reject"})
            with st.spinner("▶ Resuming graph..."):
                st.session_state["graph"].invoke(None, config)
            st.session_state["pending"] = False
            st.session_state["show_edit"] = False
            st.session_state["last_result"] = {
                "type": "reject",
                "action": action,
                "confidence": confidence,
            }
            st.rerun()

    # --- Show result ---
    if st.session_state["last_result"] and not st.session_state["pending"]:
        res = st.session_state["last_result"]
        rtype = res["type"]

        if rtype == "approve":
            st.markdown(
                f"""<div class="result-box result-approve">
                ✅ <strong>APPROVED</strong> — Action <code>{res['action']}</code> được thực thi.
                Confidence: <strong>{res['confidence']:.2%}</strong>
                </div>""",
                unsafe_allow_html=True,
            )
        elif rtype == "reject":
            st.markdown(
                f"""<div class="result-box result-reject">
                ❌ <strong>REJECTED</strong> — Action <code>{res['action']}</code> đã bị huỷ.
                Không có thay đổi nào được thực hiện.
                </div>""",
                unsafe_allow_html=True,
            )
        elif rtype == "edit":
            st.markdown(
                f"""<div class="result-box result-edit">
                ✏️ <strong>EDITED &amp; APPROVED</strong> — Original: <code>{res['original']}</code>
                → New: <code>{res['action']}</code>
                </div>""",
                unsafe_allow_html=True,
            )
        elif rtype == "auto":
            st.markdown(
                f"""<div class="result-box result-auto">
                ⚡ <strong>AUTO-EXECUTED</strong> — Action <code>{res['action']}</code> được tự động thực thi.
                Confidence: <strong>{res['confidence']:.2%}</strong> ≥ {CONFIDENCE_THRESHOLD}
                </div>""",
                unsafe_allow_html=True,
            )

    # --- Nếu chưa có gì ---
    if not st.session_state["pending"] and not st.session_state["last_result"]:
        st.markdown(
            """
            <div style='text-align:center; padding:60px 20px; color:#64748b;'>
                <div style='font-size:3rem;'>🤖</div>
                <div style='font-size:1.1rem; margin-top:12px;'>
                    Chọn Customer ID và bấm <strong style="color:#a78bfa;">▶ Run Agent</strong> để bắt đầu.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Audit Trail column
# ---------------------------------------------------------------------------

with col_audit:
    st.markdown('<div class="section-title">📜 Audit Trail</div>', unsafe_allow_html=True)

    if os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            try:
                audit_records = json.load(f)
            except json.JSONDecodeError:
                audit_records = []
    else:
        audit_records = []

    if audit_records:
        # Hiển thị mới nhất trước
        rows_html = ""
        for rec in reversed(audit_records):
            decision = rec.get("decision", "")
            decision_color = {
                "approve": "#6ee7b7",
                "reject": "#fca5a5",
                "edit": "#fde68a",
                "auto_execute": "#93c5fd",
            }.get(decision, "#e2e8f0")

            decision_icon = {
                "approve": "✅",
                "reject": "❌",
                "edit": "✏️",
                "auto_execute": "⚡",
            }.get(decision, "❓")

            rows_html += f"""
            <tr>
                <td style='color:#94a3b8; font-size:0.8rem;'>{rec.get('timestamp','')[:19]}</td>
                <td><code style='color:#c4b5fd;'>{rec.get('action','')}</code></td>
                <td style='color:#f1f5f9;'>{rec.get('confidence', 0):.0%}</td>
                <td style='color:{decision_color}; font-weight:600;'>
                    {decision_icon} {decision.replace('_', ' ').upper()}
                </td>
                <td style='color:#94a3b8; font-size:0.8rem;'>{rec.get('reviewer_id','')}</td>
            </tr>
            """

        st.markdown(
            f"""
            <table class="audit-table">
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Action</th>
                        <th>Conf</th>
                        <th>Decision</th>
                        <th>Reviewer</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(f"\n*{len(audit_records)} bản ghi — `audit_log.json`*")

        # Nút refresh
        if st.button("🔄 Refresh Audit Log", use_container_width=True):
            st.rerun()

    else:
        st.markdown(
            """
            <div style='text-align:center; padding:40px 20px; color:#475569;'>
                <div style='font-size:2rem;'>📭</div>
                <div style='margin-top:8px;'>Chưa có bản ghi nào.</div>
                <div style='font-size:0.85rem; margin-top:4px;'>
                    Audit trail sẽ xuất hiện sau khi workflow hoàn thành.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style='text-align:center; padding:32px 0 16px; color:#334155; font-size:0.8rem;'>
        Lab 27 · Human-in-the-Loop Workflow · LangGraph + Streamlit
    </div>
    """,
    unsafe_allow_html=True,
)
