"use client";

import React, { useState } from "react";
import { MOCK_WORK_ORDERS, WorkshopWorkOrder } from "@/lib/mock-data/work-orders";
import { CheckCircle2 } from "lucide-react";

export default function WorkshopDashboardView({ activeTab }: { activeTab: string }) {
  const [workOrders, setWorkOrders] = useState<WorkshopWorkOrder[]>(MOCK_WORK_ORDERS);
  const [changeOrderModal, setChangeOrderModal] = useState<WorkshopWorkOrder | null>(null);
  const [changeDesc, setChangeDesc] = useState("Front Brake Wear Sensor Severely Degraded");
  const [changeCost, setChangeCost] = useState("38");
  const [changeSent, setChangeSent] = useState(false);

  const displayedOrders = activeTab === "change_orders"
    ? workOrders.filter((wo) => wo.changeOrders && wo.changeOrders.length > 0)
    : workOrders;

  // Job Sign-off Modal
  const [signOffModal, setSignOffModal] = useState<WorkshopWorkOrder | null>(null);
  const [finalOdometer, setFinalOdometer] = useState("34825");
  const [signOffDone, setSignOffDone] = useState(false);

  const handleSendChangeOrder = (e: React.FormEvent) => {
    e.preventDefault();
    if (!changeOrderModal) return;
    setChangeSent(true);
    setTimeout(() => {
      const updated = workOrders.map((wo) => {
        if (wo.id === changeOrderModal.id) {
          return {
            ...wo,
            status: "WAITING_APPROVAL" as const,
            changeOrders: [
              ...wo.changeOrders,
              {
                id: `CO-${Date.now().toString().slice(-4)}`,
                itemDescription: changeDesc,
                additionalCost: parseFloat(changeCost) || 38,
                reason: "Technician discovery during active disassembly",
                status: "PROPOSED_PENDING_CUSTOMER" as const,
                proposedAt: new Date().toISOString()
              }
            ]
          };
        }
        return wo;
      });
      setWorkOrders(updated);
      setChangeSent(false);
      setChangeOrderModal(null);
    }, 1000);
  };

  const handleSignOff = (e: React.FormEvent) => {
    e.preventDefault();
    if (!signOffModal) return;
    setSignOffDone(true);
    setTimeout(() => {
      const updated = workOrders.map((wo) =>
        wo.id === signOffModal.id
          ? {
              ...wo,
              status: "COMPLETED" as const,
              currentOdometerRecorded: parseInt(finalOdometer) || wo.currentOdometerRecorded
            }
          : wo
      );
      setWorkOrders(updated);
      setSignOffDone(false);
      setSignOffModal(null);
    }, 1000);
  };

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Top Banner */}
      <div className="bg-purple-900 text-white rounded-3xl p-6 shadow-md border border-purple-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-black uppercase tracking-wider text-purple-200 bg-purple-800 px-2 py-0.5 rounded">
              Doc 13 Automotive Services Architecture
            </span>
            <span className="text-xs text-purple-200">• State Machine: CREATED &rarr; IN_PROGRESS &rarr; COMPLETED</span>
          </div>
          <h2 className="text-2xl font-black mt-1">
            Workshop Bay & WorkOrder Console
          </h2>
          <p className="text-xs text-purple-200 mt-1 max-w-xl">
            Customer pre-authorizes budget into Escrow. Changes require instant in-app authorization. Job sign-off writes directly to the Vehicle Master passport.
          </p>
        </div>

        <div className="bg-purple-950 p-4 rounded-2xl border border-purple-800 text-right shrink-0">
          <div className="text-xs text-purple-300 font-bold">Bay Capacity Today</div>
          <div className="text-2xl font-black text-amber-400 mt-0.5">3 / 4 Lifts Active</div>
        </div>
      </div>

      {/* Active Work Orders */}
      <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h3 className="text-base font-black text-slate-950">
              Active Bay Work Orders (Doc 13 §16)
            </h3>
            <p className="text-xs text-slate-500">
              Real-time work orders with labor tasks, diagnostic logs, and customer authorization status.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {displayedOrders.map((wo) => (
            <div
              key={wo.id}
              className="bg-slate-50 rounded-2xl border border-slate-200 p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-6 hover:bg-slate-100/60 transition-colors"
            >
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className="font-mono text-xs font-black bg-slate-950 text-amber-400 px-2 py-0.5 rounded">
                    {wo.id}
                  </span>
                  <span className="text-xs font-bold text-slate-900">{wo.customerName}</span>
                  <span className="text-slate-400">•</span>
                  <span className="text-xs text-slate-600 font-semibold">{wo.bayName}</span>

                  {wo.status === "IN_PROGRESS" && (
                    <span className="bg-blue-100 text-blue-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2">
                      IN PROGRESS
                    </span>
                  )}
                  {wo.status === "WAITING_APPROVAL" && (
                    <span className="bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2 animate-pulse">
                      WAITING CUSTOMER AUTHORIZATION
                    </span>
                  )}
                  {wo.status === "WAITING_PARTS" && (
                    <span className="bg-purple-100 text-purple-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2">
                      WAITING PARTS DISPATCH
                    </span>
                  )}
                  {wo.status === "COMPLETED" && (
                    <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2">
                      COMPLETED (WRITTEN TO GARAGE)
                    </span>
                  )}
                </div>

                <h4 className="text-base font-black text-slate-950">{wo.vehicleDisplay}</h4>
                <div className="text-xs font-semibold text-purple-700 mt-0.5">
                  {wo.serviceType} • Assigned: {wo.assignedTechnician}
                </div>

                <p className="text-xs text-slate-600 bg-white p-2.5 rounded-xl border border-slate-200 mt-2">
                  {wo.notes}
                </p>

                {wo.changeOrders.length > 0 && (
                  <div className="mt-3 p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900">
                    <strong className="font-bold">Pending ChangeOrder (Doc 13 §22):</strong> {wo.changeOrders[0].itemDescription} (+£{wo.changeOrders[0].additionalCost})
                  </div>
                )}
              </div>

              <div className="flex flex-col lg:items-end justify-between border-t lg:border-t-0 pt-4 lg:pt-0 border-slate-200 shrink-0">
                <div className="text-xl font-black text-slate-950">£{wo.finalPrice}</div>
                <div className="text-[10px] text-slate-500 mb-3">Pre-Authorized in Escrow</div>

                <div className="flex items-center gap-2">
                  {wo.status !== "COMPLETED" && (
                    <>
                      <button
                        onClick={() => {
                          setChangeOrderModal(wo);
                          setChangeDesc("Brake Pad Sensor Degradation");
                          setChangeCost("38");
                        }}
                        className="px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 text-xs font-bold rounded-xl"
                      >
                        Raise ChangeOrder
                      </button>

                      <button
                        onClick={() => {
                          setSignOffModal(wo);
                          setFinalOdometer(wo.currentOdometerRecorded.toString());
                        }}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-black rounded-xl shadow-sm"
                      >
                        Sign-Off Job
                      </button>
                    </>
                  )}
                  {wo.status === "COMPLETED" && (
                    <span className="text-xs text-emerald-700 font-bold bg-emerald-50 px-3 py-1.5 rounded-xl border border-emerald-200">
                      Vehicle Master Updated ✓
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ChangeOrder Drawer */}
      {changeOrderModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 border border-slate-200 shadow-2xl">
            <h4 className="text-base font-black text-slate-950">
              Raise ChangeOrder (Doc 13 §22)
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Work Order Ref: <strong className="font-mono text-slate-800">{changeOrderModal.id}</strong>
            </p>

            {changeSent ? (
              <div className="py-8 text-center">
                <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto animate-bounce mb-2" />
                <h5 className="text-sm font-bold text-slate-900">ChangeOrder Dispatched to Customer!</h5>
                <p className="text-xs text-slate-500 mt-1">
                  Customer alerted via In-App notification with technician photo evidence.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSendChangeOrder} className="space-y-4 mt-4 text-xs">
                <div>
                  <label className="block font-bold text-slate-600 mb-1">Additional Labor / Part Discovery</label>
                  <input
                    type="text"
                    required
                    value={changeDesc}
                    onChange={(e) => setChangeDesc(e.target.value)}
                    className="w-full h-10 px-3 border border-slate-300 rounded-xl font-bold"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-600 mb-1">Extra Amount (£)</label>
                  <input
                    type="number"
                    required
                    value={changeCost}
                    onChange={(e) => setChangeCost(e.target.value)}
                    className="w-full h-10 px-3 border border-slate-300 rounded-xl font-black text-sm"
                  />
                </div>

                <div className="p-3 bg-amber-50 rounded-xl text-amber-900 border border-amber-200">
                  <strong className="font-bold">Doc 13 Invariant:</strong> The workshop cannot charge additional items without explicit, timestamped customer authorization.
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setChangeOrderModal(null)}
                    className="px-4 py-2 border border-slate-300 rounded-xl font-bold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-purple-700 hover:bg-purple-800 text-white font-black rounded-xl"
                  >
                    Send to Customer
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Sign-Off Job Modal (Doc 13 §24 & Doc 05 Write-Back) */}
      {signOffModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 border border-slate-200 shadow-2xl">
            <h4 className="text-base font-black text-slate-950">
              Sign-Off Job & Vehicle Master Write-Back
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Work Order Ref: <strong className="font-mono text-slate-800">{signOffModal.id}</strong>
            </p>

            {signOffDone ? (
              <div className="py-8 text-center">
                <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto animate-bounce mb-2" />
                <h5 className="text-sm font-bold text-slate-900">Job Complete & Written to Vehicle Master!</h5>
                <p className="text-xs text-slate-500 mt-1">
                  Escrow payment released to workshop account. Customer digital glovebox updated.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSignOff} className="space-y-4 mt-4 text-xs">
                <div>
                  <label className="block font-bold text-slate-600 mb-1">Final Verified Odometer (Miles)</label>
                  <input
                    type="number"
                    required
                    value={finalOdometer}
                    onChange={(e) => setFinalOdometer(e.target.value)}
                    className="w-full h-10 px-3 border border-slate-300 rounded-xl font-mono font-bold text-sm"
                  />
                </div>

                <div className="p-3 bg-emerald-50 rounded-xl text-emerald-900 border border-emerald-200">
                  <strong className="font-bold">Doc 05 Rule:</strong> This mileage observation and invoice will be permanently appended to the vehicle&apos;s immutable lifecycle record.
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setSignOffModal(null)}
                    className="px-4 py-2 border border-slate-300 rounded-xl font-bold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-black rounded-xl"
                  >
                    Confirm & Disburse Payout
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
