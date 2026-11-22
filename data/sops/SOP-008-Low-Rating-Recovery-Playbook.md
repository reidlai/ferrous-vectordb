# SOP-008: Low-Rating Review Recovery & Proactive De-Escalation Playbook

**Document ID:** SOP-008  
**Category:** Customer Retention & Sentiment Recovery  
**Effective Date:** 2026-11-22  
**Version:** 1.0  
**License:** MIT / Apache-2.0 (Zero-PII Enterprise Policy)  
**Target Systems:** `ferrous-agent` (AI Copilot), `ferrous-cqrses`, `ferrous-api`

---

## 1. Purpose & Scope

When an order receives a low post-delivery satisfaction score (`review_score` of **1 or 2 stars**), this SOP guides the AI Copilot and human operators through root-cause triage, empathetic outreach, and policy-compliant recovery actions.

---

## 2. Automated Triage Signals (From Delta Lake / DataFusion)

The Copilot must correlate the low review score with objective order telemetry before recommending compensation:
1. **Delivery SLA Breach:** Check whether `order_delivered_customer_date > order_estimated_delivery_date` and compute delay hours.
2. **Carrier Stall:** Check whether `order_status != 'delivered'` past `order_estimated_delivery_date`.
3. **Prior Concessions:** Query cumulative courtesy credits on the order aggregate to confirm remaining headroom under the **$20.00 platform cap**.

---

## 3. Recovery Tiers

### 3.1 Confirmed Delivery Delay (1–2★ + Late Delivery)
- Acknowledge the exact delay duration transparently without blaming the customer.
- Recommend a HITL-approved courtesy credit under `SOP-001 §4.2` (Tier 1: up to $15.00 freight refund for 48h–96h delay; Tier 2: freight refund + $5.00 voucher capped at **$20.00 total** for >96h delay).
- **Policy Citation:** `SOP-008 §3.1`

### 3.2 On-Time Delivery With Product Quality Issue (1–2★ + On-Time)
- Do **not** issue a delivery delay credit; instead offer an immediate prepaid RMA return or instant voucher exchange under `SOP-007`.
- Flag the `seller_id` for quality-assurance review if defect rate exceeds 5% over 30 days.
- **Policy Citation:** `SOP-008 §3.2`

### 3.3 Guardrails & HITL Approval (AD-8)
- `ferrous-agent` may **draft** recovery messages and **propose** `IssueCourtesyCredit` payloads, but a human operator must approve every financial mutation in the Operator Studio Workbench.
- Never promise compensation exceeding **$20.00**; escalate higher-value claims to the Customer Support Operations Director (`SOP-001 §4.4`).
- **Policy Citation:** `SOP-008 §3.3`
