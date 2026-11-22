# SOP-004: Order Cancellation Eligibility Matrix

**Document ID:** SOP-004  
**Category:** Order Lifecycle & Fulfillment Operations  
**Effective Date:** 2026-11-22  
**Version:** 1.0  
**License:** MIT / Apache-2.0 (Zero-PII Enterprise Policy)  
**Target Systems:** `ferrous-agent` (AI Copilot), `ferrous-cqrses`, `ferrous-api`

---

## 1. Purpose & Scope

This Standard Operating Procedure (SOP) defines when an e-commerce order may be cancelled directly, placed on seller hold, intercepted in transit, or routed to a post-delivery Return Merchandise Authorization (RMA), keyed strictly to the Olist `order_status` lifecycle.

---

## 2. Cancellation Rules by `order_status`

### 2.1 `created` or `approved` (Pre-Invoice Window)
- **Eligibility:** Immediate self-service or Copilot-recommended cancellation via `OrderCommand::CancelOrder` (HITL operator confirmation required per AD-8).
- **Financial Impact:** Payment authorization is voided or reversed automatically; zero shipping fee charged.
- **Policy Citation:** `SOP-004 §2.1`

### 2.2 `invoiced` or `processing` (Seller Fulfillment Window)
- **Eligibility:** Conditional cancellation. The seller has generated a fiscal invoice or begun warehouse packing.
- **Required Action:** Dispatch a Seller Hold Request and confirm within 4 business hours whether the parcel has been handed to the carrier (`order_delivered_carrier_date` is null).
  1. If not yet handed to carrier: approve `OrderCommand::CancelOrder` and trigger full refund.
  2. If already handed to carrier: transition to §2.3 Transit Interception.
- **Policy Citation:** `SOP-004 §2.2`

### 2.3 `shipped` (In-Transit Window)
- **Eligibility:** Direct cancellation is **blocked** once `order_delivered_carrier_date` is populated.
- **Required Action:** Instruct the customer to refuse delivery at the door (zero return freight fee) or request carrier return-to-sender intercept. Refund triggers once carrier tracking confirms return scan.
- **Policy Citation:** `SOP-004 §2.3`

### 2.4 `delivered` (Post-Delivery Window)
- **Eligibility:** Cannot be cancelled; route to `SOP-007` Return & Warranty RMA workflow within the statutory/category return window.
- **Policy Citation:** `SOP-004 §2.4`
