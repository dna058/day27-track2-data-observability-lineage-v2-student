# Lab 27 — Human-in-the-Loop (HITL) Churn Risk Agent

Hệ thống Agent HITL đánh giá churn risk của khách hàng, kết hợp LangGraph workflow,
confidence routing, hard policy rules, Streamlit approval UI và audit trail.

## Cài đặt dependency

```bash
cd hitl
pip install -r requirements.txt
```

## Cách chạy LangGraph workflow (CLI test)

```bash
cd hitl
python graph.py CUST001   # high-risk → human review
python graph.py CUST002   # low-risk  → auto-execute
python graph.py CUST003   # high churn prob → human review
```

## Cách chạy Streamlit UI

```bash
cd hitl
streamlit run app.py
```

Truy cập `http://localhost:8501` trên trình duyệt.

## Confidence Threshold

```
CONFIDENCE_THRESHOLD = 0.85
```

- `confidence >= 0.85` + low-risk action → **Auto-Execute**
- `confidence < 0.85` → **Escalate to Human Review**

## Hard Policy Rule

```
increase_credit_limit → luôn Human Review (bất kể confidence)
```

Hard rule được kiểm tra **trước** confidence threshold.  
Dù confidence là `0.99`, action `increase_credit_limit` vẫn phải qua human review.

## Routing Logic

```
proposed_action
      │
      ▼
┌─────────────────────────┐
│  increase_credit_limit? │ ── YES ──► execute_high_risk_action (INTERRUPT)
└─────────────────────────┘
      │ NO
      ▼
┌─────────────────────────┐
│  confidence >= 0.85?    │ ── YES ──► execute_low_risk_action (AUTO)
└─────────────────────────┘
      │ NO
      ▼
execute_high_risk_action (INTERRUPT)
```

## Cách Approve, Reject và Edit

Sau khi graph bị interrupt:

1. **Approve** — Bấm nút `✅ Approve`, graph resume và thực thi proposed action
2. **Reject** — Bấm nút `❌ Reject`, graph resume và huỷ action
3. **Edit** — Bấm `✏️ Edit`, nhập action mới, bấm `✅ Confirm Edit`:
   - State được cập nhật với `human_decision = "edit:<action_mới>"`
   - Graph resume và thực thi action đã chỉnh sửa

## Audit Log

Lưu tại: `hitl/audit_log.json`

Mỗi quyết định tạo ra một entry:

```json
{
  "timestamp": "2026-08-29T09:00:00",
  "agent_id": "churn-risk-agent-v1",
  "action": "increase_credit_limit",
  "confidence": 0.92,
  "reviewer_id": "operator_01",
  "decision": "approve"
}
```

Audit log **không bao giờ bị overwrite** — mỗi entry được append vào danh sách.

## Cấu trúc file

```
hitl/
├── models.py        # GraphState (TypedDict) + AuditEntry (Pydantic)
├── graph.py         # Agent node, routing, graph compile
├── app.py           # Streamlit approval UI
├── audit_log.json   # Audit trail (auto-generated)
└── requirements.txt # langgraph langchain streamlit pydantic
```

## Mock Customers

| Customer ID | Churn Prob | TOI | Expected Path |
|-------------|-----------|-----|---------------|
| CUST001 | 78% | 52M VND | increase_credit_limit → Human Review |
| CUST002 | 35% | 18M VND | send_email → Auto-Execute |
| CUST003 | 91% | 120M VND | increase_credit_limit → Human Review |
| CUST004 | 55% | 30M VND | send_email → depends on confidence |
