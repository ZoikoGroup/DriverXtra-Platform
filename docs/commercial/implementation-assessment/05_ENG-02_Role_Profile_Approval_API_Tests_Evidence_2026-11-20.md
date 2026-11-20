# ENG-02 — D02 role-profile approval API tests: evidence record

| Field | Value |
|---|---|
| Record date | 20 November 2026. The work was implemented and tested on 19 November 2026. |
| IDs | Implementation **ENG-02** = gap-closure plan §4.1 **ENG-02** (same scope). Master register: no gap ID assigned. §4.1 cites the D02 finding, master test **COM-008** and **EV-04** (authorisation). |
| Nature | **Tests only.** No application code was changed. The tests exercise the existing `apps/commercial` role-profile approval rules through the admin API. |
| IMPLEMENTED | **Yes** (17 test cases added) |
| TESTED | **Yes**, on SQLite only (§2) |
| Formal status | **IMPLEMENTED – NOT VERIFIED.** No SHA binding (CD-06). The tests are uncommitted on top of `HEAD` `4107076f41b5dba269c490cbbdc8bfb059580f5d`. |
| VERIFIED IN TEST | **No** |

## 1. What the tests cover

**File:** `backend/tests/test_commercial_api.py`, in the section headed "ENG-02 — D02 role-profile approval rules exercised through the admin API". There are 9 test functions, which become 17 cases after parametrisation:

| Test | Rule |
|---|---|
| `test_role_profile_approval_requires_commercial_approve_permission` | Approval needs the `commercial.approve` permission |
| `test_role_profile_author_cannot_approve_own_profile` | Separation of duties |
| `test_gated_role_profiles_cannot_be_approved` (parametrised) | Gated profile types are blocked |
| `test_role_profile_approval_requires_legal_memo_reference` (parametrised) | A legal-memo reference is required |
| `test_role_profile_approval_requires_approval_reference` (parametrised) | An approval reference is required |
| `test_role_profile_transition_requires_reason` | Transitions need a reason |
| `test_valid_role_profile_approval_succeeds_and_is_audited` | Valid approval succeeds and is audited |
| `test_role_profile_versioning_supersedes_and_retirement_is_terminal` | Prospective-only versioning; retirement is terminal |
| `test_draft_role_profile_can_be_retired_without_approval` | A draft can be retired without approval |

**Limitation carried from D02:** the approval and legal-memo references are checked only for presence (non-empty). They are not resolved against an evidence record. That stays **BLOCKED** on BLK-04 (the evidence-record owner decision; gap-closure plan §2 row 1).

## 2. Test evidence

From `backend/`, SQLite in-memory; environment as in [04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md) §3.

| # | When (UTC, 19 Nov) | Command | Result |
|---|---|---|---|
| E2-1 | 07:54 | `.venv/Scripts/python.exe -m pytest tests/test_commercial_api.py -q -p no:cacheprovider -rfE -k "role_profile or gated"` | **18 passed, 16 deselected** (166.58 s): the 17 ENG-02 cases plus the existing `test_rate_and_role_profile_api_round_trip`, which matches the filter |
| E2-2 | 08:00 | `.venv/Scripts/python.exe -m pytest tests/test_commercial_api.py tests/test_commercial_control_plane.py -q -p no:cacheprovider -rfE` | **78 passed** (372.94 s) |
| — | 10:14 | ENG-04a 14-file regression, which included both files ([07](07_ENG-04a_Commercial_Quote_Adapter_Evidence_2026-11-20.md)) | 396 passed |

No defect was found, and no application change was needed.

## 3. Outstanding

1. **PostgreSQL:** never run on PostgreSQL.
2. **Not re-run since 19 Nov.** `apps/commercial` has not changed since, but the suite has not been re-run on the final tree.
3. **No SHA binding.**
4. **BLK-04** (reference resolution) and **BLK-06** (approved USA/UK role profiles, which depend on the D02 legal memos from GC + CFO) remain open.
