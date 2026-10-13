"use client";

import React, { useState } from "react";
import {
  Building2,
  Car,
  TrendingUp,
  Inbox,
  RefreshCw,
  Plus,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
  ShieldAlert,
  Sliders,
  DollarSign
} from "lucide-react";

export default function DealerPortalView({ onBackToMarketplace }: { onBackToMarketplace: () => void }) {
  const [syncing, setSyncing] = useState(false);

  const inventory = [
    {
      id: "INV-8491",
      title: "2024 Toyota RAV4 2.5 Hybrid Design AWD",
      vin: "JTMB1RFV50D19...",
      price: "£34,995",
      status: "ACTIVE",
      leads: 6,
      daysInStock: 8,
      source: "DMS AutoSync",
    },
    {
      id: "INV-8492",
      title: "2023 BMW X3 xDrive30e M Sport (Pro Pack)",
      vin: "WBA5R1C50M82...",
      price: "£43,500",
      status: "ACTIVE",
      leads: 11,
      daysInStock: 14,
      source: "DMS AutoSync",
    },
    {
      id: "INV-8493",
      title: "2024 Mercedes-Benz C 300 AMG Line",
      vin: "W1K2060461F...",
      price: "£39,800",
      status: "RESERVED",
      leads: 3,
      daysInStock: 4,
      source: "Direct Web Wizard",
    },
    {
      id: "INV-8494",
      title: "2022 Porsche Macan GTS PDK",
      vin: "WP1ZZZ95ZNL...",
      price: "£57,900",
      status: "PENDING_KYB",
      leads: 0,
      daysInStock: 1,
      source: "Bulk Feed (CSV)",
    },
  ];

  const handleSyncDms = () => {
    setSyncing(true);
    setTimeout(() => {
      setSyncing(false);
    }, 1200);
  };

  return (
    <div className="bg-slate-100 min-h-screen py-8 px-4 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-[1440px]">
        {/* Portal Breadcrumb & Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-slate-200 gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
              <Building2 className="w-4 h-4 text-amber-600" />
              <span>Dealer & Fleet B2B Architecture (Doc 16)</span>
              <span>/</span>
              <span className="text-slate-800">Apex Automotive Group UK</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1">
              Dealership Operations Workspace
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSyncDms}
              disabled={syncing}
              className="px-4 py-2.5 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-2 shadow-sm transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin text-amber-500" : ""}`} />
              <span>{syncing ? "Syncing DMS Feed..." : "Sync DMS Feed"}</span>
            </button>

            <button
              onClick={onBackToMarketplace}
              className="px-4 py-2.5 rounded-xl bg-slate-950 text-amber-400 hover:bg-slate-800 text-xs font-bold transition-all"
            >
              Back to Public Marketplace
            </button>
          </div>
        </div>

        {/* Top KPIs Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 my-6">
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
            <span className="text-xs font-semibold text-slate-500">Active Listings</span>
            <div className="text-2xl font-black text-slate-950 mt-1 flex items-baseline justify-between">
              <span>48 Vehicles</span>
              <span className="text-xs text-emerald-600 font-bold flex items-center">
                +4 this week
              </span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
            <span className="text-xs font-semibold text-slate-500">Escrow Held & Pending</span>
            <div className="text-2xl font-black text-slate-950 mt-1 flex items-baseline justify-between">
              <span>£84,200</span>
              <span className="text-xs text-amber-600 font-bold">2 Handover Passes</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
            <span className="text-xs font-semibold text-slate-500">Cleared Balance (Doc 10)</span>
            <div className="text-2xl font-black text-emerald-700 mt-1 flex items-baseline justify-between">
              <span>£142,650</span>
              <span className="text-xs bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded font-bold">
                Payout Ready
              </span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
            <span className="text-xs font-semibold text-slate-500">DMS Feed Health (Doc 20)</span>
            <div className="text-2xl font-black text-slate-950 mt-1 flex items-baseline justify-between">
              <span className="text-emerald-600 text-lg flex items-center gap-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-500" /> 100% Synced
              </span>
              <span className="text-xs text-slate-400">12 min ago</span>
            </div>
          </div>
        </div>

        {/* Inventory Table */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-bold text-slate-950">
                Dealer Managed Vehicle Inventory
              </h3>
              <p className="text-xs text-slate-500">
                All vehicles verified against Canonical Vehicle Master schema before publication.
              </p>
            </div>

            <button className="px-4 py-2 bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-bold rounded-lg flex items-center gap-1.5 shadow-sm">
              <Plus className="w-4 h-4" />
              <span>Create New Listing Wizard</span>
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="py-3.5 px-4">Vehicle Specs</th>
                  <th className="py-3.5 px-4">VIN Number</th>
                  <th className="py-3.5 px-4">Price</th>
                  <th className="py-3.5 px-4">State</th>
                  <th className="py-3.5 px-4">Buyer Leads</th>
                  <th className="py-3.5 px-4">Ingestion Feed</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {inventory.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-slate-900">
                      {item.title}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500">
                      {item.vin}
                    </td>
                    <td className="py-3.5 px-4 font-black text-slate-950">
                      {item.price}
                    </td>
                    <td className="py-3.5 px-4">
                      {item.status === "ACTIVE" && (
                        <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded font-bold">
                          ACTIVE (In Search)
                        </span>
                      )}
                      {item.status === "RESERVED" && (
                        <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-bold">
                          RESERVED (Escrow Locked)
                        </span>
                      )}
                      {item.status === "PENDING_KYB" && (
                        <span className="bg-purple-100 text-purple-800 px-2 py-0.5 rounded font-bold">
                          PENDING MODERATION
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-semibold text-slate-700">
                      {item.leads} active inquiries
                    </td>
                    <td className="py-3.5 px-4 text-slate-500">
                      {item.source}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button className="text-amber-600 hover:text-amber-700 font-bold">
                        Manage &rarr;
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
