# Doc COM-02 — Country Role and Funds Flow

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-02 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | GC / Compliance (gate owner for "P0: Wrong merchant/regulated role") [M§23]; co-owner CFO for price/fund-flow sign-off [M§23, M§25 D02] |
| Required approvers | GC + CFO (D02) [M§25]; Global Tax + CFO for tax/funds schedule (D09) [M§25]; CTO + CFO + GC for PSP (D04) [M§25]; cross-functional sign-off per [M§00] |
| Related decisions | D01 OPEN; D02 BLOCKED (needs D01 corridor); D04 BLOCKED (needs D01, D02); D06 RECOMMENDED (hold; switch stays OFF); D09 BLOCKED (needs D01, D02, D04) |
| Related tests | test COM-001, test COM-008, test COM-009 [M§24] |

ID-namespace note: "Doc COM-0X" = this deliverable series; "revenue code COM-0X" = M§04 codes; "test COM-0XX" = M§24 tests. They are unrelated identifiers.

Decision-status note: M§25 lists D02, D04 and D09 as OPEN; the BLOCKED statuses above are the document owner's dependency status and do not change the master recommendation.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines, per country/corridor, which legal transaction role profile applies, which funds-flow mode may carry money for it, and what evidence must exist before a country gate opens. It is the subordinate deliverable "COM-02 Country Role & Funds Flow" named in [M§25]. It covers role separation [M§02], role profiles and the activation bundle [M§09], payment modes A–F and the money-movement prohibition [M§10], the country-gate state machine [M§21], gates G0–G4 [M§22], and the data-dictionary fields `commercial_role_id` and `country_activation_version` [M App C]. Tax determination detail belongs to Doc COM-06; PSP settlement detail belongs to Doc COM-05 [M§25].

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| R02-01 | Roles (advertiser, seller of record, legal supplier, service performer, agent if appointed, platform, PSP, lender, insurer, warranty obligor, tax collector, shipper) exist as separately versioned properties, not one "marketplace seller" flag. | [M§02] |
| R02-02 | DriverXtra must not imply title to vehicles/goods, provide direct lending/insurance underwriting, or independently hold customer balances because it controls the UI. | [M§02] |
| R02-03 | Each transaction resolves jurisdiction/fulfilment location and buyer/seller legal roles before quoting. | [M§07] |
| R02-04 | `commercial_role_id` (executed, market-effective role profile) is mandatory before a binding order. | [M App C] |
| R02-05 | `country_activation_version` (signed legal-financial pack effective at transaction time) is recorded; no default permissive state. | [M App C] |
| R02-06 | A country/corridor activates only after the mandatory activation bundle (§3.4) is complete. | [M§09] |
| R02-07 | No self-operated "escrow", wallet balances, customer safeguarding or payment custody without counsel-confirmed permissions and a documented PSP role. | [M§10] |
| R02-08 | Payment modes E and F are GATED; mode B only after role, chargeback and negative-balance allocation approval. | [M§10] |
| R02-09 | Country gate states: designed → legally_reviewed → partner_verified → finance_signed → technical_rehearsed → enabled; suspended/withdrawn. | [M§21] |
| R02-10 | Regulated activities assessed activity-by-activity; no global blanket "mere referral" assumption. | [M§09] |
| R02-11 | No regulated SKU, warranty insurance or high-value settlement enabled without a signed country gate. | [M§24 test COM-008] |
| R02-12 | Role-specific legal counsel opinion and price/fund-flow sign-off per corridor. | [M§23] |
| R02-13 | "Global-first" is not simultaneous activation; activate only markets with validated payment/compliance/vendor density. | [M§22] |

## 3. Specification draft

### 3.1 Role profiles (master, RECOMMENDED)

| Role profile | Who makes the customer supply | Mandatory decision | Master label |
|---|---|---|---|
| Advertising-only | Seller/dealer contracts independently with buyer. | Platform fee buys publication/lead tools; truthful claims, ad transparency. | RECOMMENDED [M§09] |
| Software-only | Seller, workshop or fleet customer remains counterparty. | SaaS supply and data-processing roles mapped independently. | RECOMMENDED [M§09] |
| Facilitated order | Named third-party seller; PSP handles authorized collection. | Merchant-of-record, checkout liability, tax and returns per corridor. | RECOMMENDED [M§09] |
| Disclosed commercial agent | Agent acts only within executed authority. | Signed mandate; conflicts, disclosure, local agency-law opinion. | RECOMMENDED [M§09] |
| Regulated introducer | Licensed principal/provider. | FCA / US state / EU member-state perimeter, remuneration, marketing, oversight. | GATED [M§08 F, M§25 D06] |
| Cross-border orchestrator | Importer/exporter and customs owner stated; title allocation known. | Duties, sanctions, homologation, consumer rights, waste/battery. | GATED (G4 scope) [M§22] |
| Principal seller / owner | OUT OF SCOPE in asset-light default. | Board approval, insurance, liability, tax, inventory balance sheet. | OUT OF SCOPE [M§09] |

D02 recommends approving advertising, SaaS, lead and facilitated-commerce profiles separately [M§25]. The master does not list "lead" as a separate §09 row; whether lead fees sit under advertising-only or a separate profile is an open input (§6).

### 3.2 Payment modes (master)

| Mode | Funds flow / liability | Initial posture | Status here |
|---|---|---|---|
| A | Buyer → seller's PSP account; PSP disburses seller share; platform fee via valid application fee/billing. | Recommended where PSP coverage exists. | RECOMMENDED [M§10] |
| B | Buyer → PSP-controlled marketplace arrangement → seller balances and platform fee. | Only after role, chargeback, negative-balance allocation approval. | Conditional [M§10] |
| C | Buyer pays dealer via dealer-approved channels; platform charges lead/ad/SaaS independently. | Default for high-value vehicles early. | RECOMMENDED [M§10] |
| D | Business → approved billing PSP → DriverXtra contracting legal entity. | Recommended early recurring revenue. | RECOMMENDED [M§10] |
| E | PSP-managed conditional payout on validated evidence and contract rights. | Gated; never labeled legal escrow without review. | GATED — disabled [M§10] |
| F | Consumer/provider transact via provider-regulated channels; referral invoiced separately. | Gated until counsel, contracts, auditability. | GATED — disabled [M§10] |

MONEY-MOVEMENT PROHIBITION (verbatim): "DriverXtra must not self-operate 'escrow', wallet balances, customer safeguarding or payment custody without counsel-confirmed permissions and documented PSP role. A marketplace PSP may offer platform-managed delayed payout, but this is not equivalent to the platform being licensed to provide legal escrow." [M§10]

### 3.3 Role profile × payment mode matrix (master text only)

Legend: **T** = the master text links this mode to this profile (cited); **—** = master does not state the combination (open input to GC + CFO under D02/D04); **G** = GATED; **OOS** = OUT OF SCOPE. No cell is an approval; every T cell still requires D02 and per-corridor sign-off [M§23].

| Role profile | A | B | C | D | E | F | Basis |
|---|---|---|---|---|---|---|---|
| Advertising-only | — | — | T | T | G | G | Seller contracts independently [M§09]; mode C charges "lead/ad/SaaS independently" [M§10]; platform fee via billing (mode D: business → DriverXtra entity) [M§10] |
| Software-only | — | — | — | T | G | G | SaaS supply [M§09]; mode D recurring revenue [M§10]; fleet subscription journey [M§08 E] |
| Facilitated order | T | T (conditional) | — | — | G | G | "PSP handles authorized collection" [M§09]; A for approved goods/services, B after approvals [M§10]; parts/booking journeys via licensed/permitted PSP [M§08 B, C] |
| Disclosed commercial agent | — | — | — | — | G | G | No funds-flow statement in master [M§09] |
| Regulated introducer | G | G | G | G | G | G | Mode F is the only master-referenced flow and is GATED [M§10]; D06 hold [M§25] |
| Cross-border orchestrator | G | G | G | G | G | G | Cross-border is G4 scope [M§22] |
| Principal seller / owner | OOS | OOS | OOS | OOS | OOS | OOS | [M§09] |

The platform's own fee on facilitated orders: mode A states it is collected "via valid application fee/billing" [M§10]; mode B includes it in the PSP arrangement [M§10]. Which applies per corridor depends on D04.

### 3.4 Country/corridor activation checklist (tracked list)

Each item must be evidenced per country/corridor and referenced from the gate transition that consumes it. Status for every item is **Not started** (no D01 corridor selected). Owners shown as "App D" are the master's controlled owner for the corresponding policy; others are open inputs.

| # | Checklist item | Source | Evidence artifact | Candidate owner | Gate step consuming it | Status |
|---|---|---|---|---|---|---|
| CA-01 | Country-specific entity authority | [M§09] | Entity/authority memo | Open input (GC) | legally_reviewed | Not started |
| CA-02 | Tax nexus / marketplace deemed-supplier classification | [M§09, M§11] | Signed tax schedule (D09) | Global Tax [M App D] | finance_signed | Not started |
| CA-03 | Licensing and auto-dealer advertising restrictions | [M§09] | Counsel memo | Legal + Dealer Ops [M App D] | legally_reviewed | Not started |
| CA-04 | Consumer cancellation, warranty, product liability, recalls (safety-critical parts, batteries, used-part provenance) | [M§09] | Policy set | Consumer Legal + CFO; Trust + Legal [M App D] | legally_reviewed | Not started |
| CA-05 | Seller verification / trader traceability | [M§09] | KYB procedure | Compliance + Security [M App D] | partner_verified | Not started |
| CA-06 | AML/sanctions rules where applicable | [M§09] | Compliance memo | Compliance + Security [M App D] | legally_reviewed | Not started |
| CA-07 | Data protection and marketing consent | [M§09] | Privacy notice, DPA | Privacy + CTO [M App D] | legally_reviewed | Not started |
| CA-08 | PSP support, payout destinations, local card/bank rails, chargebacks, reserve policies | [M§09] | PSP schedule (D04) | Payments + CFO + GC [M App D] | partner_verified / finance_signed | Not started |
| CA-09 | If EV installation, charging, tow or repair: permits, safety accreditation, occupational scope, service insurance, emergency escalation | [M§09] | Partner credential evidence | Commercial + Risk [M App D] | partner_verified | Not started |
| CA-10 | If financing, GAP, extended warranty or insurance: activity-by-activity regulated perimeter | [M§09] | Perimeter memo | Regulatory Counsel [M App D] | GATED — not applicable while D06 hold | Disabled |
| CA-11 | Role-specific counsel opinion and price/fund-flow sign-off for the corridor | [M§23] | Signed memo per profile | GC / Compliance [M§23] | legally_reviewed / finance_signed | Not started |
| CA-12 | Sandbox rehearsal of quote, invoice, refund, tax, payout and ledger controls | [M§00, M§22] | Rehearsal record | Open input (CTO) | technical_rehearsed | Not started |
| CA-13 | Per-SKU go-live evidence pack | [M§24] | See Doc COM-13 | Open input | enabled | Not started |

The mapping of checklist items to gate steps is a drafting proposal; the master defines the states but not which evidence each state consumes (open input).

### 3.5 Country-gate state machine

`designed → legally_reviewed → partner_verified → finance_signed → technical_rehearsed → enabled`; branches `suspended`, `withdrawn` [M§21]. Only `enabled` permits binding transactions; an absent gate is closed ("no default permissive state") [M App C]. Each transaction records the `country_activation_version` in force [M App C]. Transitions emit `compliance.policy_changed` / `eligibility.suspended` [M§21 events]. Re-entry rules from `suspended`/`withdrawn` are not specified in the master (open input).

### 3.6 Gates G0–G4 (scope relevant to this document)

| Gate | Role / funds-flow content | Source |
|---|---|---|
| G0 Board design freeze | Legal role matrix, target pilot market, contracting legal entity, tax map, PSP viability. Authorizes build, not launch. | [M§22] |
| G1 Controlled pilot | Subscriptions/lead billing and reconciliation; modes C/D only implied by scope (no checkout). | [M§22, M§10] |
| G2 Transactional commerce | PSP settlement, tax, dispute resilience; enable per vertical + payment corridor after rehearsals. | [M§22] |
| G3 Enterprise marketplace | Group accounts, B2B procurement; B2B order preserves buyer and supplier entity. | [M§22, M§13.6] |
| G4 Regulated/global expansion | GATED: finance/insurance, controlled vehicle settlement, cross-border, additional countries. | [M§22] |

"Modes C/D only implied" for G1 is a drafting inference from G1 scope; confirm under D04/D08.

## 4. Engineering reconciliation notes

| Topic | Engineering text | Master position | Handling |
|---|---|---|---|
| Ownership | Country rules in CTX-17 Global Policy; payments in CTX-07; finance/insurance orchestration in CTX-13 [E 2.4] | Commercial policy entity and country gate [M§21]; Commercial Catalog / Contract & Pricing domains [M§20] | No engineering context named for commercial role profiles; assignment to CTX-17 vs a new context is an open input (CTO). |
| Seller funds held | "The seller's money is held until it is eligible for payout." [E 1.5] | Platform must not self-operate escrow, wallets or custody; holding only via a PSP role; mode E GATED [M§10] | **Conflict flagged, not resolved.** E 1.5 must be read as PSP-held delayed payout under a documented PSP role, pending D04 and counsel. |
| Buyer protection | Protection includes "buyer protection" [E 1.2] | Off-platform sales must not represent "guaranteed buyer protection"; assurance product needs legal name [M§08 D, M§23] | Flagged; product naming for counsel. |
| Finance/insurance | Platform lets people "get finance or insurance" [E 1.1]; partner decides [E 1.3, 1.7] | Mode F and regulated introducer GATED; REG-01/REG-02 OFF [M§04, M§10] | Flagged; master governs (disabled). |
| Jurisdiction packs | "No country forks. Country rules live in versioned jurisdiction packs." [E 2.2] | `country_activation_version` signed pack [M App C] | Compatible in intent; field mapping open. |
| Corporate identity | "Zoiko Tech Inc." [E 1.1] | Zoiko Mobility Inc. [M§00] | Logged inconsistency; master governs. |

## 5. Implementation evidence (repo)

Implementation evidence only; nothing below is an approval or a D01/D02 decision.

| Fact (verified) | Path |
|---|---|
| `PartyRoleProfile` with `profile_type` (seven values matching the §09 rows), `seller_of_record`, `service_performer`, `platform_role`, `payment_role`, `tax_party`, `invoice_issuer`, `licensed_partner_required`, `legal_memo_reference`, effective dates; new profiles DRAFT. | [Repo: backend/apps/commercial/models.py], [Repo: backend/apps/commercial/choices.py] |
| `PaymentRoleChoices` map modes A–F; E and F in `GATED_PAYMENT_ROLES`; regulated introducer, cross-border orchestrator, principal seller in `GATED_ROLE_PROFILE_TYPES`. Gated profiles cannot be approved; author cannot approve own profile; approval requires a legal memo reference. | [Repo: backend/apps/commercial/choices.py], [Repo: backend/apps/commercial/services/roles.py] |
| `PartyRoleSnapshot` (append-only) copies the applied roles and a `snapshot_hash` per quote. | [Repo: backend/apps/commercial/models.py] |
| `CountryGate` scoped country × vertical × capability (DISCOVERY, LEAD_CAPTURE, BINDING_QUOTE, SUBSCRIPTION_BILLING, REGULATED_REFERRAL); starts DESIGNED; `version` increments each transition; append-only `CountryGateTransition`. | [Repo: backend/apps/commercial/models.py] |
| Transitions follow the §21 sequence; legally_reviewed..technical_rehearsed need an evidence reference; enabling needs a tax schedule reference, currencies, an approved effective role profile (except DISCOVERY), a finance sign-off by a different person; regulated gates cannot be enabled. Repo also allows ENABLED↔SUSPENDED, any→WITHDRAWN and WITHDRAWN→DESIGNED (re-entry rule not in master). | [Repo: backend/apps/commercial/services/gates.py] |
| Missing gate treated as closed (`COUNTRY_GATE_CLOSED`); quote stores `gate_version` as `country_activation_version`. | [Repo: backend/apps/commercial/services/gates.py], [Repo: backend/apps/commercial/models.py] |
| Gate scope is ISO 3166-1 alpha-2 `country_code`; no corridor dimension observed. | [Repo: backend/apps/commercial/models.py] |
| India (GST) / UK (VAT) configuration exists in `platform_core/regional` and `platform_core/tax`; this is implementation, not a D01 market decision or D09 tax sign-off. | [Repo: backend/platform_core/regional/], [Repo: backend/platform_core/tax/] |
| Marketplace settings default `COD_ENABLED=True` for `IN,GB`; COD is not a §10 mode (see Doc COM-05). | [Repo: backend/config/settings.py] |

Gap observed: §02 roles advertiser, agent, lender, insurer, warranty obligor and shipper have no dedicated field in either §21 `party_role_snapshot` or the repo snapshot.

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| First pilot country/corridor | Founder + Commercial (D01) | All checklist items; D02, D04, D09 |
| Approved role profile per vertical and corridor (incl. whether "lead" is its own profile) | GC + CFO (D02) | §3.1, §3.3, gate enablement |
| Fill "—" cells of the role × mode matrix | GC + CFO (D02), CTO + CFO + GC (D04) | §3.3 |
| PSP selection and mode A vs B per corridor | CTO + CFO + GC (D04) | §3.2, CA-08 |
| Signed first-country tax, PSP funds and platform invoicing schedule | Global Tax + CFO (D09) | CA-02, gate finance_signed |
| Mapping of checklist evidence to gate states; re-entry rules after suspended/withdrawn | GC + CFO + CTO | §3.4, §3.5 |
| Corridor modeling (country pair vs country) | CTO + GC | Gate scope |
| Fields for advertiser, agent, lender, insurer, warranty obligor, shipper roles | GC + CTO | R02-01 |
| Owner for CA-01 and CA-12 | GC; CTO | §3.4 |
| Engineering context owning role profiles and gates | CTO | §4 |
| Wording for E 1.5 seller-funds statement | CTO + GC | §4 conflict |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-001 | Rule that absent/expired commercial role rejects checkout; role resolution order | [M§24, M App C] |
| test COM-008 | List of gated profiles/modes and the gate preconditions | [M§24] |
| test COM-009 | Seller-of-record identity source for labels | [M§24, M§02] |
| Evidence pack: role/legal memo | Per-profile counsel memo reference | [M§24] |
| Evidence pack: finance/tax configuration | D09 schedule reference per gate | [M§24] |
| Evidence pack: incident/rollback switch | Gate suspension path | [M§24, M§21] |

## 8. Completion status

| Section | Status |
|---|---|
| 1 Purpose and scope | Drafted |
| 2 Requirements | Drafted |
| 3.1–3.2 Profiles and modes | Drafted |
| 3.3 Matrix | Pending external input (D02, D04) |
| 3.4 Activation checklist | Pending external input (D01, D09) |
| 3.5–3.6 State machine and gates | Drafted |
| 4 Engineering reconciliation | Drafted (conflicts flagged, not resolved) |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 11 open inputs.
