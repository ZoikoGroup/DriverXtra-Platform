"use client";

import React, { useState } from "react";
import {
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  UserCheck,
  Scale,
  Lock,
  Search,
  Eye,
  FileText,
  Activity
} from "lucide-react";

export default function AdminOpsView({ onBackToMarketplace }: { onBackToMarketplace: () => void }) {
  const [makerCheckerOpen, setMakerCheckerOpen] = useState(false);
  const [actionApproved, setActionApproved] = useState(false);

  const pendingQueues = [
    {
      id: "CASE-4912",
      type: "DISPUTE_REMEDY",
      title: "Refund Request: Incompatible Brake Calipers (£480)",
      maker: "Alex Miller (Dispute Analyst)",
      reason: "Guaranteed Fit assertion mismatch. Return receipt confirmed by carrier.",
      riskLevel: "HIGH (Financial Outflow)",
      status: "AWAITING_CHECKER_APPROVAL",
    },
    {
      id: "KYB-1082",
      type: "DEALER_ONBOARDING",
      title: "Apex Bavarian Group: Organization KYB Approval",
      maker: "Elena Rostova (Trust Analyst)",
      reason: "Companies House, VAT registration and bank mandate certified.",
      riskLevel: "CRITICAL (Platform Privileges)",
      status: "AWAITING_CHECKER_APPROVAL",
    },
    {
      id: "FLAG-9011",
      type: "ODOMETER_ANOMALY",
      title: "Vehicle Listing JTMB1RFV... Mileage Discrepancy",
      maker: "System Fraud Watchdog (Doc 11)",
      reason: "Listing states 12k mi; DVLA MOT record reports 38k mi in 2025.",
      riskLevel: "CRITICAL (Marketplace Fraud)",
      status: "QUARANTINED_PENDING_REVIEW",
    },
  ];

  const handleApproveAction = () => {
    setActionApproved(true);
    setTimeout(() => {
      setMakerCheckerOpen(false);
      setActionApproved(false);
    }, 1500);
  };

  return (
    <div className="bg-slate-900 min-h-screen py-8 px-4 sm:px-6 lg:px-10 text-white">
      <div className="mx-auto max-w-[1440px]">
        {/* Environment / Session Elevation Banner (Wireframe Doc 24 §15) */}
        <div className="bg-amber-500/20 border border-amber-500/40 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-3">
            <span className="w-3 h-3 rounded-full bg-amber-400 animate-ping"></span>
            <div className="text-xs">
              <strong className="text-amber-300 font-bold">OPERATIONS CONTROL PLANE:</strong> Environment: <strong className="text-white">UK-PRODUCTION-CELL-01</strong> • Elevated JIT Privilege Session • Immutable Audit Logging Active
            </div>
          </div>
          <button
            onClick={onBackToMarketplace}
            className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-bold transition-all text-slate-200"
          >
            Exit Operations Console
          </button>
        </div>

        {/* Console Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-slate-800 gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-white">
              Marketplace Operations & Governance Console
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Doc 24 Specification: Zero omnibus privileges. All consequential administrative actions require Four-Eyes (Maker-Checker) dual sign-off.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300">
              Active Checker: <strong>Senior Ops Lead</strong>
            </span>
          </div>
        </div>

        {/* Queues Overview */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 my-6">
          <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5">
            <span className="text-xs font-semibold text-slate-400">Maker-Checker Approval Queue</span>
            <div className="text-2xl font-black text-amber-400 mt-1 flex items-baseline justify-between">
              <span>3 Pending</span>
              <span className="text-xs text-amber-400 font-bold">SLA: 18m remaining</span>
            </div>
          </div>

          <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5">
            <span className="text-xs font-semibold text-slate-400">Trust & Risk Escalations (Doc 11)</span>
            <div className="text-2xl font-black text-rose-400 mt-1 flex items-baseline justify-between">
              <span>1 Quarantined</span>
              <span className="text-xs text-slate-400">Fraud Flag</span>
            </div>
          </div>

          <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5">
            <span className="text-xs font-semibold text-slate-400">Open Disputes Under Adjudication</span>
            <div className="text-2xl font-black text-emerald-400 mt-1 flex items-baseline justify-between">
              <span>12 Cases</span>
              <span className="text-xs text-emerald-400 font-bold">All within SLA</span>
            </div>
          </div>
        </div>

        {/* Maker-Checker Approval List */}
        <div className="bg-slate-800/90 border border-slate-700 rounded-2xl p-6 shadow-xl">
          <div className="flex items-center justify-between pb-4 border-b border-slate-700">
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Scale className="w-4 h-4 text-amber-400" />
                Four-Eyes (Maker-Checker) Work Queue
              </h3>
              <p className="text-xs text-slate-400">
                Actions proposed by operational staff awaiting secondary executive sign-off before committing to the database.
              </p>
            </div>
          </div>

          <div className="space-y-4 mt-4">
            {pendingQueues.map((item) => (
              <div
                key={item.id}
                className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4"
              >
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="font-mono text-xs font-bold text-amber-400 bg-amber-950/80 border border-amber-800 px-2 py-0.5 rounded">
                      {item.id}
                    </span>
                    <span className="text-xs font-bold text-slate-300">{item.type}</span>
                    <span className="text-xs text-rose-400 font-bold bg-rose-950/60 border border-rose-800 px-2 py-0.5 rounded ml-2">
                      {item.riskLevel}
                    </span>
                  </div>

                  <h4 className="text-base font-bold text-white">{item.title}</h4>
                  <p className="text-xs text-slate-400 mt-1">
                    Proposed by: <strong className="text-slate-200">{item.maker}</strong> • Reason: {item.reason}
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <button
                    onClick={() => setMakerCheckerOpen(true)}
                    className="px-4 py-2.5 bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-black rounded-lg shadow flex items-center gap-1.5"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Authorize as Checker</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Checker Modal */}
        {makerCheckerOpen && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl text-white">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <h3 className="text-base font-bold text-amber-400 flex items-center gap-2">
                  <Lock className="w-4 h-4" />
                  Maker-Checker Dual Authorization
                </h3>
                <button
                  onClick={() => setMakerCheckerOpen(false)}
                  className="text-slate-400 hover:text-white"
                >
                  ✕
                </button>
              </div>

              {actionApproved ? (
                <div className="py-8 text-center">
                  <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-2 animate-bounce" />
                  <h4 className="text-base font-bold text-white">Action Authorized & Executed!</h4>
                  <p className="text-xs text-slate-400 mt-1">
                    Immutable audit record #AUD-98219 committed to PostgreSQL. Ledger payout released.
                  </p>
                </div>
              ) : (
                <div className="space-y-4 mt-4">
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs">
                    <div className="text-slate-400 font-semibold">Action to Execute:</div>
                    <div className="font-bold text-white text-sm mt-1">
                      Execute Buyer Protection Remedy: £480.00 Refund to Buyer
                    </div>
                    <div className="text-slate-400 mt-2">
                      Case Ref: <span className="font-mono text-amber-400">CASE-4912</span>
                    </div>
                  </div>

                  <div className="text-xs text-slate-300">
                    By submitting your credential elevation, you confirm that you have reviewed the carrier return evidence, verified seller lack of response, and authorize the double-entry refund ledger entry.
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button
                      onClick={() => setMakerCheckerOpen(false)}
                      className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-300"
                    >
                      Reject Action
                    </button>
                    <button
                      onClick={handleApproveAction}
                      className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-xs font-black text-white flex items-center gap-1.5 shadow"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Confirm & Commit Audit Trail</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
