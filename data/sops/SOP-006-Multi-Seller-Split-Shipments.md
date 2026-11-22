# SOP-006: Multi-Seller Split Shipments & Staggered Delivery Resolution

**Document ID:** SOP-006  
**Category:** Marketplace Logistics & Fulfillment  
**Effective Date:** 2026-11-22  
**Version:** 1.0  
**License:** MIT / Apache-2.0 (Zero-PII Enterprise Policy)  
**Target Systems:** `ferrous-agent` (AI Copilot), `ferrous-api` (DataFusion Lakehouse)

---

## 1. Purpose & Scope

Marketplace orders frequently contain multiple items (`order_item_id = 1, 2, ...`) fulfilled by different independent sellers (`seller_id`). This SOP defines how the Copilot explains staggered deliveries and resolves partial-shipment complaints.

---

## 2. Diagnostic Checklist

Before issuing a missing-item claim or courtesy credit, the Copilot must verify via `ferrous-api` / DataFusion:
1. Count distinct `seller_id` values associated with the `order_id`.
2. Compare each item's `shipping_limit_date` and carrier handoff timestamp (`order_delivered_carrier_date`).
3. Confirm whether the customer received Parcel 1 of N while Parcel 2 is still within its `order_estimated_delivery_date` window.

---

## 3. Resolution Playbook

### 3.1 Remaining Items Still Within SLA Window
- Reassure the customer that items from separate marketplace sellers ship in independent parcels with separate tracking numbers.
- Provide the estimated delivery date for each outstanding parcel; no concession is required while within SLA.
- **Policy Citation:** `SOP-006 §3.1`

### 3.2 One Seller Breaches SLA (>48 Hours Late)
- Calculate freight reimbursement strictly on the delayed item's `freight_value` (not the entire multi-seller order total).
- Apply `SOP-001 §4.2` Tier 1 (48h–96h) or Tier 2 (>96h) courtesy credit rules, respecting the **$20.00 aggregate ceiling**.
- **Policy Citation:** `SOP-006 §3.2`

### 3.3 Missing Item From Same Seller Parcel
- If all items share a single `seller_id` and tracking confirms delivery of one parcel with missing units, escalate immediately under `SOP-003` (Customer Dispute Resolution) for seller fulfillment audit and replacement or item-level refund.
- **Policy Citation:** `SOP-006 §3.3`
