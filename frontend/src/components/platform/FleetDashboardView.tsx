"use client";

import React, { useState } from "react";
import { MOCK_FLEET_VEHICLES, FleetVehicleItem } from "@/lib/mock-data/fleet";
import { AlertTriangle } from "lucide-react";

export default function FleetDashboardView({ activeTab }: { activeTab: string }) {
  const [fleet, setFleet] = useState<FleetVehicleItem[]>(MOCK_FLEET_VEHICLES);
  const [assignModal, setAssignModal] = useState<FleetVehicleItem | null>(null);
  const [newDriver, setNewDriver] = useState("David Palmer (Badge #209)");

  const displayedFleet = activeTab === "maintenance_due"
    ? fleet.filter((v) => v.operationalStatus === "MAINTENANCE_DUE" || v.operationalStatus === "GROUNDED_DEFECT")
    : fleet;

  const handleSaveDriver = (e: React.FormEvent) => {
    e.preventDefault();
    if (!assignModal) return;
    const updated = fleet.map((v) =>
      v.id === assignModal.id ? { ...v, assignedDriver: newDriver } : v
    );
    setFleet(updated);
    setAssignModal(null);
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
            Commercial Fleet Management
          </span>
        </div>
      </div>

      {/* Top Fleet KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Active Fleet Units
          </span>
          <div className="text-2xl font-black text-slate-950 mt-1 flex items-baseline justify-between">
            <span>{fleet.length} Commercial Units</span>
            <span className="text-xs text-emerald-600 font-bold">100% In Service</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Maintenance Due Alerts
          </span>
          <div className="text-2xl font-black text-amber-600 mt-1 flex items-baseline justify-between">
            <span>1 Unit Due</span>
            <span className="text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded font-bold">
              LD23 MBZ
            </span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Monthly Operating Cost
          </span>
          <div className="text-2xl font-black text-slate-950 mt-1">
            £1,030.00
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Open RFQs / Requisitions
          </span>
          <div className="text-2xl font-black text-purple-700 mt-1">
            2 Requisitions
          </div>
        </div>
      </div>

      {/* Fleet Portfolio Table */}
      <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black uppercase tracking-wider text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
                Fleet Operations
              </span>
              <span className="text-xs text-slate-500">• Vehicle Master Operational Extensions</span>
            </div>
            <h3 className="text-lg font-black text-slate-950 mt-1">
              Enterprise Fleet Portfolio Register
            </h3>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
              <tr>
                <th className="py-3.5 px-4">Unit Code & Vehicle</th>
                <th className="py-3.5 px-4">Registration</th>
                <th className="py-3.5 px-4">Assigned Driver</th>
                <th className="py-3.5 px-4">Operating Pool</th>
                <th className="py-3.5 px-4">Current Mileage</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium">
              {displayedFleet.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-3.5 px-4 font-bold text-slate-950">
                    <div className="font-mono text-amber-700 text-xs">{item.unitCode}</div>
                    <div className="text-slate-900">{item.vehicleDisplay}</div>
                  </td>
                  <td className="py-3.5 px-4 font-mono font-bold text-slate-800">
                    {item.registrationPlate}
                  </td>
                  <td className="py-3.5 px-4 text-slate-700 font-bold">
                    {item.assignedDriver}
                  </td>
                  <td className="py-3.5 px-4 text-slate-500">
                    {item.assignedPool}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-slate-800">
                    {item.currentMileage.toLocaleString()} mi
                  </td>
                  <td className="py-3.5 px-4">
                    {item.operationalStatus === "ACTIVE_SERVICE" && (
                      <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-2 py-0.5 rounded">
                        ACTIVE SERVICE
                      </span>
                    )}
                    {item.operationalStatus === "MAINTENANCE_DUE" && (
                      <span className="bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded flex items-center gap-1 w-fit">
                        <AlertTriangle className="w-3 h-3" /> MAINTENANCE DUE
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <button
                      onClick={() => setAssignModal(item)}
                      className="px-2.5 py-1 text-xs font-bold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition-colors"
                    >
                      Reassign
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Driver Assignment Modal */}
      {assignModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 border border-slate-200 shadow-2xl">
            <h4 className="text-base font-black text-slate-950">
              Reassign Driver for {assignModal.unitCode}
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">{assignModal.vehicleDisplay}</p>

            <form onSubmit={handleSaveDriver} className="space-y-4 mt-4 text-xs">
              <div>
                <label className="block font-bold text-slate-600 mb-1">Select Driver</label>
                <input
                  type="text"
                  required
                  value={newDriver}
                  onChange={(e) => setNewDriver(e.target.value)}
                  className="w-full h-10 px-3 border border-slate-300 rounded-xl font-bold"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setAssignModal(null)}
                  className="px-4 py-2 border border-slate-300 rounded-xl font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-black rounded-xl"
                >
                  Confirm Assignment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
