# P1/P2 Screen Backlog

| Field | Value |
|---|---|
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Requirements sources | Master DX-COMM-MASTER-001 (v1.0; v1.1 rev. B proposed), `../01_Engineering_Reconciliation_Matrix.md`, Doc COM-02..COM-13 drafts in `../com/` |
| Confirmed decisions used | Zoiko Mobility Inc.; markets USA and UK; Stripe preferred (verification pending); finance and insurance out of scope here (separate workstream, Rithika) |
| API status legend | **CONFIRMED** = the route and method exist in the repository today (verified against the Django URL configuration on 19 November 2026; existing does not mean production-ready). **PROPOSED** = not in the repository; no contract implied. **DISABLED** = the route exists but the capability is closed by a gate, decision or test mode. |

| Priority | ID | Screen / capability | Role | Master | Backend state |
|---|---|---|---|---|---|
| P1 | EV-01 | EV Gateway hub: chargers, installers, battery checks | Customer | M§13.4 | No EV backend; partner sources not selected |
| P1 | VEH-04 | Vehicle order: off-platform payment report and documents | Buyer / seller | M§08D, §10 mode C | APIs exist (vehicle-orders, documents) |
| P1 | VEH-05 | Dealer storefront page | Visitor | M§14 For Dealers | Proposed |
| P1 | ORD-07 | Disputes: buyer case view and messages | Customer | M§16; E 1.6 | APIs exist |
| P1 | REV-01 | Reviews: write, reply, report; seller reputation | Customer / seller | M§16 Service quality | APIs exist |
| P1 | NTF-01 | Notification center | All | E 2.4 Notifications | APIs exist |
| P1 | SUP-01 | Support tickets (customer and agent) | Customer / agent | M§16 incident | APIs exist |
| P1 | WSH-01 | WorkshopHub: bookings board, quotations, work orders, technicians, change orders | Workshop | M§13.6 WorkshopHub | APIs exist |
| P1 | WSH-02 | Workshop profile, services and opening hours management | Workshop | M§13.3 | APIs exist |
| P1 | ORG-01 | Organisation and multi-location members | Dealer group / fleet | M§05 parent/group contracting | APIs exist |
| P1 | FIN-A1 | Finance Admin: PSP reconciliation, payout exceptions, close pack (Doc COM-10) | Finance | M§15 Finance Admin | Not implemented; Stripe verification pending |
| P1 | FIN-A2 | Invoices and credit notes | Business customer / finance | M§11 | Not implemented |
| P1 | SUB-01 | Subscription checkout, plan change, proration, cancellation | Business customer | M§05; test COM-015 | Not implemented; D03 |
| P1 | TRU-01 | Trust & compliance console: KYB, recalls, takedowns | Trust staff | M§15, §16 | Partly (application review exists) |
| P1 | HLP-01 | Help & Trust center: roles, refunds, disputes, scam warnings | Visitor | M§14 Help & Trust | Content pending counsel |
| P1 | FLT-01 | FleetOps dashboard | Fleet manager | M§13.6 | UI shell exists (FleetDashboardView); no fleet backend |
| P2 | ADS-01 | Sponsored placement purchase and campaign reporting | Dealer / advertiser | M§04 ADV-02, MKT-01 | Not implemented; no approved SKU |
| P2 | EXE-01 | Executive / board dashboard | Executive | M§15, §19 | Not implemented |
| P2 | RVO-01 | Growth / RevOps console | Commercial | M§15 | Not implemented |
| P2 | PRM-01 | Promotions administration | Commercial | M§07 Promotions | Not implemented |
| P2 | API-01 | Developer portal: API keys, quotas, webhooks | OEM / enterprise | M§05 Infrastructure API | Not implemented |
| P2 | B2B-01 | B2B RFQ and procurement approvals | Fleet / supplier | M§13.6 | Not implemented |
| P2 | FEED-01 | Dealer and supplier bulk feeds | Dealer / supplier | M§13.1, §13.2 | Not implemented |
| P2 | RSA-01 | Roadside and recovery requests | Customer | M§13.5 | Not implemented |
| P2 | LOY-01 | Loyalty and partner benefits | Customer | M§03 Loyalty | Not implemented |
| — | F&I | Finance and insurance journeys | — | M§13.7; D06 | Out of scope here: separate workstream (Rithika) |
