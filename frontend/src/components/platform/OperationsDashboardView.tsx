"use client";

import React, { useState } from "react";
import { MOCK_OPS_QUEUE, MakerCheckerTask } from "@/lib/mock-data/ops-queue";
import { CheckCircle2, Lock } from "lucide-react";

export default function OperationsDashboardView({ activeTab }: { activeTab: string }) {
  const [tasks, setTasks] = useState<MakerCheckerTask[]>(MOCK_OPS_QUEUE);
  const [activeTaskModal, setActiveTaskModal] = useState<MakerCheckerTask | null>(null);
  const [actionDone, setActionDone] = useState(false);

  const displayedTasks = activeTab === "trust_kyb"
    ? tasks.filter((t) => t.type === "DEALER_KYB_APPROVAL")
    : activeTab === "disputes_admin"
    ? tasks.filter((t) => t.type === "DISPUTE_REMEDY_REFUND" || t.type === "ODOMETER_FRAUD_FLAG")
    : tasks;

  const handleApproveAction = () => {
    if (!activeTaskModal) return;
    setActionDone(true);
    setTimeout(() => {
      const updated = tasks.map((t) =>
        t.id === activeTaskModal.id ? { ...t, status: "APPROVED" as const } : t
      );
      setTasks(updated);
      setActionDone(false);
      setActiveTaskModal(null);
    }, 1000);
  };

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Demo Data Notice */}
      <div className="flex items-center justify-between pb-1">
        <div className="inline-flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-100 text-amber-900 border border-amber-300">
            Demo data
          </span>
          <span className="text-xs text-slate-500 font-medium">
            Internal Operations Control Plane (Doc 24) • Simulated Prototype Data
          </span>
        </div>
      </div>
      {/* Session Elevation Banner (Wireframe Doc 24 §15) */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 text-white flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl">
        <div className="flex items-center gap-3">
          <span className="w-3.5 h-3.5 rounded-full bg-amber-400 animate-ping shrink-0"></span>
          <div className="text-xs">
            <div className="font-bold text-amber-300">
              OPERATIONS CONTROL PLANE (DOC 24 SPECIFICATION)
            </div>
            <div className="text-slate-400 mt-0.5">
              Active Session: <strong className="text-white">UK-PRODUCTION-CELL-01</strong> • Elevated JIT Privilege • Immutable Audit Log Stream
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs bg-slate-800 text-slate-300 font-bold px-3 py-1.5 rounded-xl border border-slate-700">
            Four-Eyes Checker Mode Active
          </span>
        </div>
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Maker-Checker Work Queue
          </span>
          <div className="text-2xl font-black text-amber-600 mt-1 flex items-baseline justify-between">
            <span>{tasks.filter((t) => t.status === "PENDING_CHECKER_APPROVAL").length} Pending</span>
            <span className="text-xs text-amber-600 font-bold">SLA: 18m</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Trust & Fraud Flags (Doc 11)
          </span>
          <div className="text-2xl font-black text-rose-600 mt-1 flex items-baseline justify-between">
            <span>1 Quarantined</span>
            <span className="text-xs text-rose-600 font-bold">Odometer Anomaly</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Open Dispute Cases (Doc 15)
          </span>
          <div className="text-2xl font-black text-emerald-700 mt-1 flex items-baseline justify-between">
            <span>12 Cases</span>
            <span className="text-xs text-emerald-700 font-bold">All within SLA</span>
          </div>
        </div>
      </div>

      {/* Maker-Checker Work Queue Table */}
      <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black uppercase tracking-wider text-rose-700 bg-rose-100 px-2 py-0.5 rounded">
                Doc 24 §15 Maker-Checker
              </span>
              <span className="text-xs text-slate-500">• Four-Eyes Dual Sign-Off Invariant</span>
            </div>
            <h3 className="text-lg font-black text-slate-950 mt-1">
              High-Risk Action Approval Queue
            </h3>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          {displayedTasks.map((task) => (
            <div
              key={task.id}
              className="p-6 flex flex-col lg:flex-row lg:items-center justify-between gap-6 hover:bg-slate-50/80 transition-colors"
            >
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className="font-mono text-xs font-black bg-slate-950 text-amber-400 px-2.5 py-1 rounded-lg">
                    {task.id}
                  </span>
                  <span className="text-xs font-bold text-slate-700">{task.type}</span>
                  <span className="bg-rose-100 text-rose-800 text-[10px] font-black px-2 py-0.5 rounded ml-2">
                    {task.riskLevel} RISK
                  </span>
                  {task.status === "APPROVED" && (
                    <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto">
                      CHECKER AUTHORIZED ✓
                    </span>
                  )}
                  {task.status === "PENDING_CHECKER_APPROVAL" && (
                    <span className="bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto animate-pulse">
                      PENDING CHECKER SIGN-OFF
                    </span>
                  )}
                </div>

                <h4 className="text-base font-black text-slate-950">{task.title}</h4>
                <div className="text-xs text-slate-500 mt-1">
                  Proposed by: <strong className="text-slate-800">{task.makerName} ({task.makerRole})</strong>
                </div>

                <p className="text-xs text-slate-600 bg-slate-50 p-2.5 rounded-xl border border-slate-200 mt-2">
                  <strong className="text-slate-900 font-bold">Operational Justification:</strong> {task.reason}
                </p>
                <div className="text-[11px] text-slate-500 mt-1">
                  Evidence: {task.evidenceSummary}
                </div>
              </div>

              <div className="shrink-0 flex items-center gap-3">
                {task.status === "PENDING_CHECKER_APPROVAL" ? (
                  <button
                    onClick={() => setActiveTaskModal(task)}
                    className="px-4 py-2.5 bg-slate-950 hover:bg-slate-800 text-amber-400 text-xs font-black rounded-xl shadow-sm flex items-center gap-2"
                  >
                    <Lock className="w-3.5 h-3.5 text-amber-400" />
                    <span>Authorize as Checker</span>
                  </button>
                ) : (
                  <span className="text-xs text-emerald-700 font-bold bg-emerald-50 px-3 py-1.5 rounded-xl border border-emerald-200">
                    Committed to Audit Trail
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Checker Dual Sign-off Modal */}
      {activeTaskModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 border border-slate-200 shadow-2xl space-y-4">
            <h4 className="text-base font-black text-slate-950 flex items-center gap-2">
              <Lock className="w-4 h-4 text-amber-500" />
              Maker-Checker Authorization Sign-Off
            </h4>
            <p className="text-xs text-slate-500">
              Task Ref: <strong className="font-mono text-slate-900">{activeTaskModal.id}</strong>
            </p>

            {actionDone ? (
              <div className="py-8 text-center">
                <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto animate-bounce mb-2" />
                <h5 className="text-sm font-bold text-slate-900">Action Authorized & Executed!</h5>
                <p className="text-xs text-slate-500 mt-1">
                  Immutable audit record written to PostgreSQL. Ledger transaction unblocked.
                </p>
              </div>
            ) : (
              <div className="space-y-4 text-xs">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <div className="font-bold text-slate-800 text-sm">{activeTaskModal.title}</div>
                  <div className="text-slate-500 mt-1">{activeTaskModal.reason}</div>
                </div>

                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-950">
                  <strong className="font-bold">Doc 24 Four-Eyes Invariant:</strong> As the secondary checker, you affirm that you have examined the factual evidence bundle and authorize the execution.
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    onClick={() => setActiveTaskModal(null)}
                    className="px-4 py-2 border border-slate-300 rounded-xl font-bold"
                  >
                    Reject
                  </button>
                  <button
                    onClick={handleApproveAction}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-black rounded-xl flex items-center gap-1.5"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Authorize & Commit</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
