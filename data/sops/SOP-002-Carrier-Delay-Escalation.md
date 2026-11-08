# SOP-002: Carrier Delay Escalation Protocols

**Document ID:** SOP-002  
**Category:** Logistics Operations & Carrier Management  
**Effective Date:** 2026-10-01  
**Version:** 1.4  
**Target Systems:** Logistics Hub Monitors, `ferrous-streaming` Carrier SLA aggregators

---

## 1. Purpose & Scope

This Standard Operating Procedure outlines the escalation protocols and operational intervention workflows for identifying, tracking, and resolving carrier delays across distribution hubs in Brazil (including Correios, Jadlog, and Loggi networks).

---

## 2. Section 2.1: Carrier Tracking Anomalies & Hub Bottlenecks

### 2.1.1 Detection Criteria
A carrier tracking anomaly is triggered when an order meets any of the following telemetry criteria:
- **Stationary Transit Event**: Tracking status remains unchanged for more than 72 hours at a major distribution center (e.g., São Paulo Gateway Hub or Rio de Janeiro Sorting Facility).
- **Missed Scan Interval**: Carrier fails to provide a physical handover scan within 24 hours of warehouse fulfillment dispatch.
- **Routing Divergence**: Parcel routing scan indicates destination state divergence (misrouted package).

### 2.1.2 Monitoring Infrastructure
Logistics tracking anomalies are detected in real-time by Arroyo stream processors reading from the Iggy `orders/intake` topic and materialized into Delta Lake tables for analytical aggregation in Apache DataFusion.

---

## 3. Section 2.2: Tier 1 to Tier 2 Logistics Escalation

When a tracking anomaly exceeds 72 hours:
1. **Tier 1 Customer Support**:
   - Verify carrier tracking code against carrier API webservice.
   - Notify customer of proactive monitoring status.
   - Check if the shipment qualifies for Goodwill Policy §4.2 under SOP-001 if delivery SLA has breached.
2. **Tier 2 Logistics Liaison Escalation**:
   - Open a high-priority incident ticket directly with carrier dispatch operations.
   - Dispatch an automated package tracer request via EDI / REST endpoint.
   - Set escalation ticket SLA for carrier response within 24 hours.

---

## 4. Section 2.3: Carrier Notification SLA & Remediation

- If the carrier confirms parcel loss, initiate immediate replacement order processing or full order refund via the CQRS command intake.
- If the carrier confirms hub congestion, adjust estimated delivery dates (EDD) and trigger customer notification with proactive tracking links.
- Maintain carrier breach logs for monthly vendor SLA reconciliation and penalty assessments.
