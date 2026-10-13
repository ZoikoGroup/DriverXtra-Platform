// Canonical Operations & Maker-Checker Data Model Grounded in Doc 24 & Doc 11

export interface MakerCheckerTask {
  id: string;
  type: "DISPUTE_REMEDY_REFUND" | "DEALER_KYB_APPROVAL" | "ODOMETER_FRAUD_FLAG" | "PAYOUT_MANUAL_RELEASE";
  title: string;
  makerName: string;
  makerRole: string;
  proposedAt: string;
  targetEntityId: string;
  amountMinor?: number;
  reason: string;
  evidenceSummary: string;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: "PENDING_CHECKER_APPROVAL" | "APPROVED" | "REJECTED";
}

export const MOCK_OPS_QUEUE: MakerCheckerTask[] = [
  {
    id: "MC-TASK-4912",
    type: "DISPUTE_REMEDY_REFUND",
    title: "Issue Buyer Protection Remedy: £480.00 Refund",
    makerName: "Alex Miller",
    makerRole: "DISPUTE_ANALYST",
    proposedAt: "2026-10-13T09:40:00Z",
    targetEntityId: "CASE-4912",
    amountMinor: 48000,
    reason: "Guaranteed Fitment mismatch. Buyer returned goods; carrier delivery receipt verified.",
    evidenceSummary: "Photo evidence of 320mm rotor provided vs 348mm vehicle requirement. Return label scanned delivered.",
    riskLevel: "HIGH",
    status: "PENDING_CHECKER_APPROVAL"
  },
  {
    id: "MC-TASK-1082",
    type: "DEALER_KYB_APPROVAL",
    title: "Apex Automotive Group UK: KYB Verification Clearance",
    makerName: "Elena Rostova",
    makerRole: "TRUST_ANALYST",
    proposedAt: "2026-10-13T08:15:00Z",
    targetEntityId: "ORG-DEALER-0182",
    reason: "Companies House filing, VAT Certificate, and FCA Consumer Credit permissions validated.",
    evidenceSummary: "Verification provider (Sumsub/Jumio) passed with zero adverse sanctions or PEP flags.",
    riskLevel: "CRITICAL",
    status: "PENDING_CHECKER_APPROVAL"
  },
  {
    id: "MC-TASK-9011",
    type: "ODOMETER_FRAUD_FLAG",
    title: "Quarantine Vehicle Listing JTMB1RFV... for Odometer Rollback",
    makerName: "Automated Fraud Watchdog",
    makerRole: "AI_RISK_PIPELINE",
    proposedAt: "2026-10-13T07:30:00Z",
    targetEntityId: "INV-8491",
    reason: "Listing states 12,000 miles; authoritative DVLA MOT record in 2025 recorded 38,400 miles.",
    evidenceSummary: "26,400 mile negative variance detected between national database and seller input.",
    riskLevel: "CRITICAL",
    status: "PENDING_CHECKER_APPROVAL"
  }
];
