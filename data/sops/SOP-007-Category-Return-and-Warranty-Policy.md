# SOP-007: Product Category Return Windows, Handling & Warranty Policy

**Document ID:** SOP-007  
**Category:** Returns, Exchanges & Category Compliance  
**Effective Date:** 2026-11-22  
**Version:** 1.0  
**License:** MIT / Apache-2.0 (Zero-PII Enterprise Policy)  
**Target Systems:** `ferrous-agent` (AI Copilot), `ferrous-api`

---

## 1. Purpose & Scope

This SOP maps return eligibility, inspection criteria, and warranty tiers to the English product categories from Olist (`product_category_name_translation.csv`), enabling category-aware Copilot guidance without exposing any customer PII.

---

## 2. Standard 7-Day Cooling-Off & 30-Day Defect Return Policy

- **Buyer Remorse / Change of Mind:** Unopened or unused items in original packaging are eligible for return within **7 calendar days** of `order_delivered_customer_date` with prepaid return label.
- **Manufacturing Defect / Damaged on Arrival:** Eligible for free replacement or full refund within **30 calendar days** (90 days for durable goods).
- **Policy Citation:** `SOP-007 §2`

---

## 3. Category-Specific Rules

### 3.1 Hygiene & Personal Care (`health_beauty`, `perfumery`, `diapers_and_hygiene`, `food_drink`)
- **Return Eligibility:** Non-returnable for buyer remorse once the tamper-evident seal is broken.
- **Damaged / Expired Exception:** Full refund or immediate replacement upon photo verification; no physical return shipment required for items under $15.00.
- **Policy Citation:** `SOP-007 §3.1`

### 3.2 Electronics & High-Value Goods (`computers_accessories`, `telephony`, `electronics`, `consoles_games`, `watches_gifts`, `audio`, `tablets_printing_image`)
- **Warranty Tier:** 90-day marketplace defect coverage plus 12-month manufacturer warranty referral.
- **Return Inspection:** Serial number and accessories checklist required at RMA intake; refund releases within 48 hours of warehouse scan.
- **Policy Citation:** `SOP-007 §3.2`

### 3.3 Bulky & Fragile Home Goods (`furniture_decor`, `bed_bath_table`, `housewares`, `home_appliances`, `garden_tools`, `office_furniture`)
- **Handling & Freight:** Scheduled carrier home-pickup provided at no cost for damaged or defective bulky items (`product_weight_g > 10000`).
- **Partial Damage Option:** Customer may opt for a one-time minor-cosmetic courtesy credit (up to **$20.00 ceiling** per `SOP-001`) to keep the item rather than arranging bulky pickup.
- **Policy Citation:** `SOP-007 §3.3`

### 3.4 Fashion, Sports & General Merchandise (`sports_leisure`, `fashion_bags_accessories`, `toys`, `baby`, `pet_shop`, `auto`, `stationery`, `books_general_interest`)
- **Return Eligibility:** Standard 7-day remorse / 30-day defect return with drop-off QR code; instant size/color exchange via store voucher (`SOP-005 §2.3`).
- **Policy Citation:** `SOP-007 §3.4`
