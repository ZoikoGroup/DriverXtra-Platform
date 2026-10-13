"use client";

import React, { useState } from "react";
import {
  Wrench,
  Car,
  Clock,
  CheckCircle2,
  AlertCircle,
  Plus,
  FileText,
  DollarSign,
  ArrowRight,
  ShieldCheck,
  Send
} from "lucide-react";

export default function WorkshopBayView({ onBackToMarketplace }: { onBackToMarketplace: () => void }) {
  const [changeOrderOpen, setChangeOrderOpen] = useState(false);
  const [changeOrderSent, setChangeOrderSent] = useState(false);

  const workOrders = [
    {
      id: "WO-98421",
      customer: "Mark Harrison",
      vehicle: "2021 BMW 330i M Sport (GF21 XTR)",
      service: "Major Service & MOT Test",
      status: "IN_PROGRESS",
      bay: "Bay 3 (Lift A)",
      tech: "David Kowalski",
      total: "£289.00",
      notes: "Customer authorized initial quote. Brake fluid flush completed.",
    },
    {
      id: "WO-98422",
      customer: "Sarah Jenkins",
      vehicle: "2023 Tesla Model 3 (LO23 FGH)",
      service: "Cabin Filter & Air Con Purge",
      status: "WAITING_APPROVAL",
      bay: "Bay 1 (EV Bay)",
      tech: "Liam O'Connor",
      total: "£165.00",
      notes: "ChangeOrder #CO-02 sent: Worn wiper blades (£34). Awaiting in-app approval.",
    },
    {
      id: "WO-98423",
      customer: "Michael Patel",
      vehicle: "2020 Audi A4 Avant (KW20 BCD)",
      service: "Front Brake Pads & Rotors",
      status: "WAITING_PARTS",
      bay: "Bay 4",
      tech: "Alex Reed",
      total: "£340.00",
      notes: "Brembo parts arriving via DriverXtra parts delivery carrier by 14:00.",
    },
  ];

  const handleSendChangeOrder = (e: React.FormEvent) => {
    e.preventDefault();
    setChangeOrderSent(true);
    setTimeout(() => {
      setChangeOrderOpen(false);
      setChangeOrderSent(false);
    }, 1500);
  };

  return (
    <div className="bg-slate-100 min-h-screen py-8 px-4 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-[1440px]">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-slate-200 gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
              <Wrench className="w-4 h-4 text-purple-600" />
              <span>Automotive Services Architecture (Doc 13)</span>
              <span>/</span>
              <span className="text-slate-800">Apex Bavarian Workshop Bay</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1">
              Workshop Bay & WorkOrder Console
            </h1>
          </div>

          <button
            onClick={onBackToMarketplace}
            className="px-4 py-2.5 rounded-xl bg-slate-950 text-amber-400 hover:bg-slate-800 text-xs font-bold transition-all"
          >
            Back to Public Marketplace
          </button>
        </div>

        {/* Status notice */}
        <div className="my-6 bg-purple-50 border border-purple-200 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-6 h-6 text-purple-700 shrink-0" />
            <div className="text-xs text-purple-900">
              <strong className="font-bold">Authoritative Service Write-Back Active:</strong> Upon technician job sign-off, completed tasks and verified odometer readings are immutably appended to the customer’s Vehicle Master record in PostgreSQL.
            </div>
          </div>
          <button
            onClick={() => setChangeOrderOpen(true)}
            className="px-3.5 py-2 bg-purple-700 hover:bg-purple-800 text-white rounded-lg text-xs font-bold shrink-0 flex items-center gap-1.5 shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Raise ChangeOrder</span>
          </button>
        </div>

        {/* Work Orders List */}
        <div className="space-y-4">
          {workOrders.map((order) => (
            <div
              key={order.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-6"
            >
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className="font-mono text-xs font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                    {order.id}
                  </span>
                  <span className="font-bold text-xs text-slate-900">{order.customer}</span>
                  <span className="text-slate-400">•</span>
                  <span className="text-xs text-slate-600 font-semibold">{order.bay}</span>

                  {order.status === "IN_PROGRESS" && (
                    <span className="bg-blue-100 text-blue-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2">
                      IN PROGRESS
                    </span>
                  )}
                  {order.status === "WAITING_APPROVAL" && (
                    <span className="bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2 animate-pulse">
                      WAITING CUSTOMER APPROVAL
                    </span>
                  )}
                  {order.status === "WAITING_PARTS" && (
                    <span className="bg-purple-100 text-purple-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2">
                      PARTS DISPATCHED
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-black text-slate-950">
                  {order.vehicle}
                </h3>
                <div className="text-sm font-semibold text-amber-600 mt-0.5">
                  {order.service} • Assigned: {order.tech}
                </div>

                <p className="text-xs text-slate-500 mt-2 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  {order.notes}
                </p>
              </div>

              <div className="flex flex-col lg:items-end justify-between border-t lg:border-t-0 pt-4 lg:pt-0 border-slate-100">
                <div className="text-xl font-black text-slate-950">{order.total}</div>
                <div className="text-[10px] text-slate-500 mb-3">Pre-authorized in Escrow</div>

                <div className="flex items-center gap-2">
                  <button className="px-3.5 py-2 border border-slate-300 rounded-lg text-xs font-bold hover:bg-slate-50">
                    Inspect Checklist
                  </button>
                  <button className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold shadow-sm">
                    Sign-Off & Write to Garage
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Change-Order Modal */}
        {changeOrderOpen && (
          <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-base font-bold text-slate-950 flex items-center gap-2">
                  <Plus className="w-4 h-4 text-purple-600" />
                  Raise Digital ChangeOrder (Doc 13 §22)
                </h3>
                <button
                  onClick={() => setChangeOrderOpen(false)}
                  className="text-slate-400 hover:text-slate-600 font-bold"
                >
                  ✕
                </button>
              </div>

              {changeOrderSent ? (
                <div className="py-8 text-center">
                  <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-2 animate-bounce" />
                  <h4 className="text-base font-bold text-slate-900">ChangeOrder Dispatched!</h4>
                  <p className="text-xs text-slate-500 mt-1">
                    Customer received an urgent In-App approval notification with attached technician photos.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleSendChangeOrder} className="space-y-4 mt-4">
                  <div>
                    <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                      Work Order Reference
                    </label>
                    <input
                      type="text"
                      disabled
                      value="WO-98421 (2021 BMW 330i)"
                      className="w-full h-10 px-3 bg-slate-100 border border-slate-200 rounded-lg text-xs font-mono font-bold"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                      Additional Item / Discovery
                    </label>
                    <input
                      type="text"
                      defaultValue="Front Brake Wear Sensors severely degraded"
                      className="w-full h-10 px-3 border border-slate-300 rounded-lg text-xs font-semibold"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                      Extra Labor & Parts Amount (£)
                    </label>
                    <input
                      type="number"
                      defaultValue="38"
                      className="w-full h-10 px-3 border border-slate-300 rounded-lg text-xs font-bold"
                    />
                  </div>

                  <div className="p-3 bg-amber-50 rounded-lg border border-amber-200 text-xs text-amber-900">
                    <strong className="font-bold">Governance Rule:</strong> The workshop cannot charge extra without explicit, timestamped customer authorization in the mobile or web app.
                  </div>

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setChangeOrderOpen(false)}
                      className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-bold"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="px-4 py-2 bg-purple-700 hover:bg-purple-800 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow-sm"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>Send Customer Authorization Request</span>
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
