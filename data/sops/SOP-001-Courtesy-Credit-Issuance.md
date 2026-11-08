# SOP-001: Courtesy Credit Issuance & Goodwill Policy

**Document ID:** SOP-001  
**Category:** Customer Experience & Financial Concessions  
**Effective Date:** 2026-10-01  
**Version:** 2.1  
**Target Systems:** `ferrous-agent` (AI Copilot), `ferrous-cqrses`, `ferrous-api`

---

## 1. Purpose & Scope

This Standard Operating Procedure (SOP) defines the operational guidelines, eligibility criteria, and financial boundaries for issuing customer courtesy credits, freight reimbursements, and goodwill concessions within the FerrousCX customer experience platform.

This policy applies to all customer-facing agents, operations supervisors, and autonomous AI copilot recommendations (`ferrous-agent`).

---

## 2. Regulatory & Architectural Context

All concessions issued under this SOP must adhere to CQRS domain invariants established in `ferrous-cqrses`:
- Concessions are financial mutations requiring explicit authorization via `OrderCommand::IssueCourtesyCredit`.
- Every concession command must reference an authoritative policy citation in the `policy_citation` field.
- Automated or human-in-the-loop concessions are bounded by a strict platform ceiling of **$20.00** (or equivalent BRL currency ceiling `R$ 100,00`). Any command violating this ceiling is rejected by the CQRS aggregate validation.

---

## 3. Section 4.1: General Concession Principles

Customer satisfaction concessions must adhere to strict financial invariants. All courtesy credit transactions require human-in-the-loop (HITL) operator authorization or automated copilot recommendation validation against policy invariants. Under no circumstances may an automated concession exceed the platform ceiling of $20.00 (or equivalent in local currency).

---

## 4. Section 4.2: Goodwill Policy §4.2: Delivery Delay Courtesy Credit Rules & Carrier Breach Compensation Thresholds

Under **Goodwill Policy §4.2**, when a shipment experiences an SLA delivery delay breaching carrier service level agreements, customer support agents and the AI Copilot are authorized to issue delivery delay courtesy credits according to the following rules:

### 4.2.1 Delivery Delay Courtesy Credit Rules
- **Eligibility Window**: Orders that have passed the promised SLA delivery estimated date by more than 48 hours without carrier delivery confirmation.
- **SLA Delivery Delay Courtesy Credit Rules**:
  1. If delay is between 48 hours and 96 hours (2 to 4 days past promised SLA delivery date), the customer is eligible for a full shipping fee refund or courtesy credit voucher.
  2. If delay exceeds 96 hours (4 days past promised SLA delivery date), the incident constitutes a severe carrier SLA breach. The customer is eligible for a full freight refund plus a goodwill merchandise courtesy credit voucher.
  3. **VIP / Repeat Customer Consideration**: For customers with high lifetime loyalty (e.g., 4 or more completed purchases, such as Aline Rocha), company policy recommends providing an immediate full refund of the shipping fee (e.g., R$ 29,80 freight value) to restore customer goodwill and prevent churn.

### 4.2.2 Carrier Breach Compensation Thresholds
- **Tier 1 Carrier Delay (48h - 96h breach)**: Compensation threshold up to 100% of freight value (capped at $15.00).
- **Tier 2 Carrier Delay (>96h breach / lost in transit risk)**: Compensation threshold up to 100% of freight value plus $5.00 courtesy credit voucher, subject to the overall $20.00 hard platform ceiling.
- **Carrier Subrogation**: All carrier breach concessions are tagged for subrogation recovery against the carrier logistics contract (Correios, Jadlog, Loggi).

### 4.2.3 Policy Citation & Audit Requirements
Any courtesy credit issued or recommended under this section must explicitly cite `Goodwill Policy §4.2` in the dispatch payload:
```json
{
  "order_id": "7a12b4e892c451",
  "customer_id": "c928410294b",
  "amount_cents": 1500,
  "currency": "BRL",
  "reason": "Carrier delivery delay exceeding 4 days in São Paulo hub",
  "policy_citation": "Goodwill Policy §4.2",
  "authorized_by": "Carlos (Operator CM)"
}
```

---

## 5. Section 4.3: Financial Invariant Verification

Before executing any courtesy credit issuance, the system performs sequential invariant checks:
1. Aggregate lifetime concession cap check for the customer.
2. Hard ceiling enforcement: Reject transaction if `amount > $20.00`.
3. Idempotency validation: Check monotonic UUIDv7 event sequence to avoid double credit issuance.

---

## 6. Section 4.4: Escalation & Exceptions

Exceptions requiring credit amounts greater than $20.00 must be escalated to the Customer Support Operations Director and cannot be processed via the standard automated copilot workflow.
