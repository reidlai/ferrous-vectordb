# SOP-005: Payment Method Refund SLAs & Settlement Rules

**Document ID:** SOP-005  
**Category:** Billing, Payments & Financial Settlement  
**Effective Date:** 2026-11-22  
**Version:** 1.0  
**License:** MIT / Apache-2.0 (Zero-PII Enterprise Policy)  
**Target Systems:** `ferrous-agent` (AI Copilot), `ferrous-cqrses`, `order-saga`

---

## 1. Purpose & Scope

This SOP establishes refund processing timelines, installment reversal rules, and customer communication templates for every Olist `payment_type` (`credit_card`, `boleto`, `voucher`, `debit_card`).

---

## 2. Refund Timelines by `payment_type`

### 2.1 `credit_card` (Including Installment Plans)
- **Processing SLA:** Acquirer reversal initiated within 2 business days; refund appears on the customer's card statement within **1 to 2 billing cycles** depending on card issuer cut-off dates.
- **Installments (`payment_installments > 1`):** Full remaining balance is credited back in a single statement adjustment or remaining installments are cancelled per issuer policy.
- **Policy Citation:** `SOP-005 §2.1`

### 2.2 `boleto` (Bank Slip / Cash Payment)
- **Processing SLA:** Refunded via direct bank transfer within **5 to 10 business days** after bank account verification, OR converted to an instant store `voucher` at the customer's election.
- **Zero-PII Rule:** Operators and Copilots must never ask for or store full banking credentials in chat transcripts; route the customer to the verified self-service payout portal.
- **Policy Citation:** `SOP-005 §2.2`

### 2.3 `voucher` (Store Credit / Gift Voucher)
- **Processing SLA:** Reissued **instantly (within 15 minutes)** upon cancellation or RMA receipt confirmation. Valid for 180 days across all marketplace categories.
- **Policy Citation:** `SOP-005 §2.3`

### 2.4 `debit_card`
- **Processing SLA:** Reversed directly to the originating checking account within **3 to 7 business days**.
- **Policy Citation:** `SOP-005 §2.4`

---

## 3. Partial Refunds & Courtesy Credits

- Courtesy credits for delivery delays or goodwill gestures are governed by `SOP-001 §4.2` and strictly bounded by the **$20.00 hard platform ceiling** enforced by `ferrous-cqrses`.
- Split payments (e.g., `voucher` + `credit_card` across multiple `payment_sequential` rows) are refunded proportionally in reverse sequential order.
