# DriverXtra Wireframes

| Field | Value |
|---|---|
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Requirements sources | Master DX-COMM-MASTER-001 (v1.0; v1.1 rev. B proposed), `../01_Engineering_Reconciliation_Matrix.md`, Doc COM-02..COM-13 drafts in `../com/` |
| Confirmed decisions used | Zoiko Mobility Inc.; markets USA and UK; Stripe preferred (verification pending); finance and insurance out of scope here (separate workstream, Rithika) |
| API status legend | **CONFIRMED** = the route and method exist in the repository today (verified against the Django URL configuration on 19 November 2026; existing does not mean production-ready). **PROPOSED** = not in the repository; no contract implied. **DISABLED** = the route exists but the capability is closed by a gate, decision or test mode. |

| File | Content |
|---|---|
| `P0_Wireframes.html` | Clickable low-fidelity wireframes for all 51 P0 screens. Desktop/mobile toggle, USA/UK market toggle, light/dark. Click actions and navigation to move between screens. Each screen shows its full specification. |
| `01_Screen_Inventory.md` | Inventory of P0 screens and backlog, with the per-screen specification in text |
| `02_P1_P2_Backlog.md` | P1/P2 screens |
| `03_Unresolved_Requirements.md` | Open requirements that block or shape the designs |

Open `P0_Wireframes.html` directly in a browser; it has no external dependencies.
Regenerate from the generator script if the screen data changes; do not edit the HTML by hand.
