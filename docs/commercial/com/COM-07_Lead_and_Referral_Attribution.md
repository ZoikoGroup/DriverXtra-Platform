# Doc COM-07 — Lead and Referral Attribution

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-07 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | Product + Commercial — controlled owner of "Ads/sponsorship labeling, rankings and lead attribution/dispute rules" [M App D]; Commercial / Risk is gate owner for "P0: Fraudulent/unqualified lead charges" [M§23] |
| Required approvers | Commercial owner proposes; CFO approves; legal/tax approves roles/territory [M§07 Approval]; CFO + Commercial (D03) [M§25]; GC + CFO for the lead role profile (D02) [M§25] |
| Related decisions | D03 first 8 SKUs — OPEN; D02 legal transaction roles — BLOCKED (needs D01); D06 regulated products — RECOMMENDED (hold; switch stays OFF); D01 first market — OPEN |
| Related tests | test COM-004, test COM-009; also test COM-008 (regulated referrals) [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines the qualified-lead and partner-referral attribution model: lead capture, validation, deduplication, acceptance, fee earning and reversal for revenue codes ADV-04, REF-01 and REF-02 [M§04], following journey A "Verified lead / partner introduction" [M§08] and the lead state machine [M§21]. It is the "COM-07 Lead/Referral Attribution" deliverable in M§25.

GATED and disabled: REG-01 consumer finance introduction and REG-02 insurance introduction ("OFF until approved…") [M§04]; journey F [M§08]; DX-REG-REF "No rate proposed" [M§06]; D06 hold [M§25]. This document specifies nothing that enables them.

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| LEAD-R01 | ADV-04 earning event: unique, consented, valid qualified lead accepted against an objective SLA. | [M§04] |
| LEAD-R02 | REF-01 earning event: verified partner acceptance with disclosure and deduplication. | [M§04] |
| LEAD-R03 | REF-02 earning event: contract-defined referral or completed job where permitted. | [M§04] |
| LEAD-R04 | REG-01 / REG-02 remain OFF (GATED). | [M§04], [M§25 D06] |
| LEAD-R05 | Never charge a fee on an unconfirmed lead or a nonbillable lead rejection. | [M§04] |
| LEAD-R06 | Do not monetize personal data through implied consent. | [M§04] |
| LEAD-R07 | Journey A: search → partner listing and disclosure → consented enquiry → validation/dedup → acceptance/rejection within SLA → optional partner outcome → fee earned per signed contract → invoice or self-bill as lawful → collections/credit note. | [M§08 A] |
| LEAD-R08 | Do not report lead "sales" as actual vehicle/finance/insurance GMV; lead-influenced downstream value is not GMV. | [M§08 A], [M§19], [M§17 Attributed GMV] |
| LEAD-R09 | Dealer-led sale: dealer/lead fee only if the defined event occurs; label "transaction completed off DriverXtra". | [M§08 D] |
| LEAD-R10 | Attribution: consented channels, UTM, dedupe, last-qualified-touch vs contract-defined event; no fees for leads from unauthorized data acquisition. | [M§18 Attribution] |
| LEAD-R11 | `qualified_lead`: source/consent, unique fingerprint, scoring rule, partner acceptance deadline, invalid reason, billable flag. | [M§21] |
| LEAD-R12 | Lead states: received → screened → qualified → accepted OR rejected/expired → fee_pending → earned/voided → invoiced/credited. | [M§21] |
| LEAD-R13 | Events `lead.qualified`, `lead.accepted`, `fee.earned`, `invoice.issued`, versioned with business ID, correlation ID, actor/source, UTC timestamp, event ID, idempotency key. | [M§21] |
| LEAD-R14 | Duplicate lead: two submissions with same customer/provider/vehicle within contractual dedupe window → one potential billable lead maximum; partner acceptance required. | [M App A] |
| LEAD-R15 | Fraud controls include synthetic leads, collusion, click farms, account sharing. | [M§16] |
| LEAD-R16 | Countermeasure: dedupe, consent, serviceable geography, partner acceptance and appeal evidence. | [M§23] |
| LEAD-R17 | Qualified lead fee recognition risk: fake/duplicate leads; rejection windows and clawback. | [M§11] |
| LEAD-R18 | `consent_provenance_id`: purpose notice version, user action, clock time, lawful channel basis. | [M App C] |
| LEAD-R19 | No promise of guaranteed lead quantity on For Dealers surface. | [M§14] |
| LEAD-R20 | Paid placement separately labeled; no ranking deception; sponsorship cannot buy verification. | [M§04 ADV-02], [M§05], [M§16] |
| LEAD-R21 | Metric: lead yield = accepted billable leads / verified inbound leads; revenue per accepted lead and invalid-lead rejection tracked; KPI "lead accepted %". | [M§17], [M§19] |
| LEAD-R22 | Consoles: Seller/Dealer — verified leads, source attribution, disputes; Growth/RevOps — leads, partner attribution. | [M§15] |
| LEAD-R23 | G1 pilot scope includes consented lead capture and lead billing. | [M§22] |
| LEAD-R24 | Contract clauses for mixed revenue streams must define non-duplication or affirmative stackable charges. | [M§04], [M§07 Stacking] |

## 3. Specification draft

### 3.1 Lead-bearing SKUs (ILLUSTRATIVE only)

| SKU | Revenue code | Master basis | Status |
|---|---|---|---|
| DX-LEAD-DEALER | ADV-04 | $5–$35; only accepted qualified lead under dedupe, consent and definition controls | ILLUSTRATIVE [M§06] |
| DX-REF-EV | REF-01 | $5–$40; accepted, nonduplicate eligible EV services lead | ILLUSTRATIVE [M§06] |
| (REF-02 SKU) | REF-02 | No SKU in M§06 | Open input |
| DX-REG-REF | REG-01/REG-02 | No rate proposed | GATED [M§06] |

### 3.2 Qualified-lead record (M§21 fields; content of each to be defined)

| Field | Definition required | Owner of definition |
|---|---|---|
| source / consent | Channel, UTM, `consent_provenance_id` [M§18], [M App C] | Product + Privacy |
| unique fingerprint | Must at minimum collapse same customer/provider/vehicle within the dedupe window [M App A] | Product + Commercial |
| scoring rule | "Objective" qualification criteria [M§04 ADV-04] | Open input |
| partner acceptance deadline | Partner SLA [M§04], [M§08 A] | Open input (per contract) |
| invalid reason | Reason codes, incl. duplicate, fraud, out-of-territory [M§24 test COM-004] | Product + Risk |
| billable flag | Set only on acceptance; never on rejected/expired/duplicate [M§04], [M§24] | Commercial |

### 3.3 State machine and fee rules

| State (M§21) | Entry condition | Fee effect |
|---|---|---|
| received | Consented enquiry captured [M§08 A] | None |
| screened | Validation/dedup/fraud checks run [M§08 A], [M§16] | None |
| qualified | Scoring rule passed; emits `lead.qualified` [M§21] | None |
| accepted | Partner accepts within SLA; emits `lead.accepted`; accepted only once [M§24 test COM-004] | Moves to fee_pending |
| rejected / expired | Partner rejects or deadline passes | No fee [M§04] |
| fee_pending → earned | Contract-defined earning event [M§08 A]; `fee.earned` [M§21] | Fee earned |
| voided | Successful appeal/clawback per contract [M§11], [M§23] | Fee reversed |
| invoiced / credited | Invoice or self-bill as lawful; credit note [M§08 A] | See Doc COM-04 / Doc COM-06 |

Attribution rule selection ("last-qualified-touch vs contract-defined event") is per contract [M§18]; this document does not choose a default.

### 3.4 Fraud and dispute controls

Required controls: synthetic leads, collusion, click farms, account sharing [M§16]; dedupe, consent, serviceable geography, partner acceptance and appeal evidence [M§23]; no fees on leads from unauthorized data acquisition [M§18]. Lead attribution/dispute rules are a required policy owned by Product + Commercial [M App D]. Appeal window, evidence standard and clawback horizon are open inputs.

### 3.5 Reporting separation

Lead revenue is reported as platform revenue only on earning; lead-implied retail value is excluded from attributed GMV [M§17], [M§19]. Account range 4300–4399 "Eligible partner referrals and sponsorship" is ILLUSTRATIVE [M App B].

## 4. Engineering reconciliation notes

| Topic | Note (flagged, not resolved) | Source |
|---|---|---|
| Ownership | E 2.4 has no dedicated lead context. Candidates: CTX-08 Services and Bookings, CTX-16 Advertising, CTX-04 Listings and Offers. Master §20 groups "Lead & Booking" (attribution, consent, qualified lead, appointments). **Ownership is OPEN — CTO decision; this document does not choose.** | [E 2.4], [M§20] |
| Fraud | CTX-09 Trust and Verification owns "verification and fraud"; lead screening likely consumes it — to confirm. | [E 2.4] |
| Regulated referrals | E 1.8 describes commissions on finance/insurance referrals; master keeps REG-01/REG-02 OFF (GATED). Master wins. | [E 1.8], [M§04] |
| Sponsored separation | E 1.9 / 2.4 "Advertising is kept separate from organic results" aligns with LEAD-R20. | [E 1.9], [E 2.4] |
| APIs | Master `POST /v1/leads`, `POST /v1/leads/{id}/decision` are "examples only"; reconcile against the API master. | [M§21] |
| Corporate identity | Engineering doc says "Zoiko Tech Inc."; master: Zoiko Mobility Inc. Logged inconsistency. | [E 1.1], [M§00] |

## 5. Implementation evidence (repo)

| Finding | Path |
|---|---|
| Leads are listed under "Not in R1" of the commercial control plane. | [Repo: backend/apps/commercial/README.md] |
| Choices exist: revenue codes ADV-04, REF-01, REF-02, REG-01, REG-02 (REG-01/REG-02 in `GATED_REVENUE_CODES`); fee basis `PER_ACCEPTED_LEAD`; gate capability `LEAD_CAPTURE`. No R1 service consumes `LEAD_CAPTURE` beyond generic gate CRUD (binding quotes check `BINDING_QUOTE` only). | [Repo: backend/apps/commercial/choices.py], [Repo: backend/apps/commercial/services/gates.py], [Repo: backend/apps/commercial/services/quotes.py] |
| Seed loads DX-LEAD-DEALER (ADV-04) and DX-REF-EV (REF-01) as ILLUSTRATIVE, `PER_ACCEPTED_LEAD`, `PER_EVENT`, no rates; DX-REG-REF as DRAFT, GATED. | [Repo: backend/apps/commercial/management/commands/seed_illustrative_commercial_catalogue.py] |
| `VehicleEnquiry` (marketplace): buyer→seller enquiry on an approved vehicle listing; fields listing, buyer, seller, organisation, message, buyer_phone, status (NEW/RESPONDED/CLOSED), seller notes/reply, timestamps. Endpoint `POST /api/v1/marketplace/vehicles/<id>/enquire/`. Anti-spam: 10 per buyer per hour; 60-second cooldown per buyer+listing. | [Repo: backend/apps/marketplace/models.py], [Repo: backend/apps/marketplace/views.py], [Repo: backend/apps/marketplace/urls.py] |
| `VehicleEnquiry` is **not** a `qualified_lead` implementation: no consent provenance, fingerprint, scoring, acceptance deadline, invalid reason, billable flag, or M§21 lead states; it emits no `lead.*` events. Its 60-second cooldown is a spam control, not a contractual dedupe window. | Same as above |
| No `lead.qualified` / `lead.accepted` events, lead endpoints, attribution/UTM capture, or referral model found. | [Repo: backend/apps/commercial/README.md "Events"], search of `backend/apps`, `backend/platform_core` |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| Engineering owner context for leads (CTX-08 / CTX-16 / CTX-04 or other) | CTO | Build allocation |
| Objective qualification/scoring rule per SKU | Commercial + Product | `qualified` state, ADV-04 |
| Partner acceptance SLA / deadline | Commercial (per contract, Doc COM-09) | `accepted`/`expired` |
| Contractual dedupe window and fingerprint keys | Commercial + Product | test COM-004, App A vector |
| Attribution rule per contract (last-qualified-touch vs contract event) | Commercial | Fee earning |
| Appeal window, evidence standard, clawback horizon | Commercial + Risk; CFO for clawback accounting | `voided`, M§11 |
| REF-02 SKU definition and rate basis | CFO + Commercial | REF-02 |
| Lead rates (beyond ILLUSTRATIVE bands) | CFO (D03) | Billing |
| Lead role profile (advertising-only vs other) | GC + CFO (D02) | Gate enablement |
| Consent notice and lawful channel basis per country | Privacy + GC | `consent_provenance_id` |
| Serviceable-geography definition | Commercial (D01 corridor) | Out-of-territory rejection |
| Lead invoicing vs self-billing determination | Global Tax (Doc COM-06) | `invoiced` |
| Lead attribution/dispute policy text | Product + Commercial (App D) | Publication |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-004 | Lead accepted only once within SLA; duplicates/fraud/rejected/out-of-territory never generate fees; golden case = App A Duplicate lead | [M§24], [M App A] |
| test COM-009 | Listing/search surfaces show seller-of-record and sponsored labels consistently on lead-bearing listings | [M§24] |
| test COM-008 | DX-REG-REF / REG-01 / REG-02 cannot be enabled without signed country gate | [M§24] |
| test COM-016 | Lead-influenced value never posted as GMV or revenue | [M§24] |
| Evidence pack | Fee specification, versioned contract (partner SLA), disclosure screenshots, golden vectors, KPI baseline (lead yield) | [M§24], [M§17] |

## 8. Completion status

| Section | Status |
|---|---|
| 1 Purpose and scope | Drafted |
| 2 Requirements | Drafted |
| 3.1 SKUs | Drafted (ILLUSTRATIVE; REF-02 pending) |
| 3.2 Record definitions | Pending external input |
| 3.3 State machine and fee rules | Drafted |
| 3.4 Fraud/dispute | Drafted; parameters pending external input |
| 4 Engineering reconciliation | Drafted; ownership open |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 13 open inputs; lead ownership context OPEN (CTO).
