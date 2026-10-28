"use client";

import React, { useState } from "react";
import { MOCK_GARAGE_VEHICLES, VehicleInstance } from "@/lib/mock-data/vehicles";
import { MOCK_ORDERS, PlatformOrder } from "@/lib/mock-data/orders";
import { MOCK_CATALOG_PARTS } from "@/lib/mock-data/parts";
import {
  Car,
  Plus,
  ShieldCheck,
  Gauge,
  Calendar,
  CheckCircle2,
  FileText,
  Lock,
  QrCode,
  AlertCircle
} from "lucide-react";

export default function ConsumerDashboardView({ activeTab }: { activeTab: string }) {
  const [vehicles, setVehicles] = useState<VehicleInstance[]>(MOCK_GARAGE_VEHICLES);
  const [selectedVehicle, setSelectedVehicle] = useState<VehicleInstance>(MOCK_GARAGE_VEHICLES[0]);
  const [orders] = useState<PlatformOrder[]>(MOCK_ORDERS);
  const [activeHandoverModal, setActiveHandoverModal] = useState<PlatformOrder | null>(null);

  // Add vehicle modal state
  const [addVehicleOpen, setAddVehicleOpen] = useState(false);
  const [newReg, setNewReg] = useState("");
  const [newVin, setNewVin] = useState("");
  const [resolvingVin, setResolvingVin] = useState(false);

  const handleResolveAndAdd = (e: React.FormEvent) => {
    e.preventDefault();
    setResolvingVin(true);
    setTimeout(() => {
      const addedVehicle: VehicleInstance = {
        id: `veh_custom_${Date.now()}`,
        vin: newVin || "WBA3A5C50DF918231",
        registrationPlate: newReg.toUpperCase() || "KV22 XYZ",
        make: "Audi",
        model: "A3 Sportback",
        year: 2022,
        trim: "35 TFSI S Line S Tronic",
        engineCode: "DADA",
        fuelType: "PETROL",
        transmission: "DUAL_CLUTCH",
        powerBhp: 150,
        currentOdometer: 18200,
        motExpiryDate: "2028-03-12",
        motStatus: "VALID",
        activeRecallsCount: 0,
        ownershipStatus: "VERIFIED_OWNER",
        primaryImageUrl: "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=800&q=80",
        serviceHistory: []
      };
      setVehicles([addedVehicle, ...vehicles]);
      setSelectedVehicle(addedVehicle);
      setResolvingVin(false);
      setAddVehicleOpen(false);
      setNewReg("");
      setNewVin("");
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
            Vehicle Garage & Consumer Portal
          </span>
        </div>
      </div>
      {/* Tab: My Garage (Doc 05) */}
      {(activeTab === "garage" || activeTab === "default") && (
        <div className="space-y-6">
          {/* Header Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-200 gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-wider text-amber-700 bg-amber-100 px-2 py-0.5 rounded">
                  Vehicle Master Passport
                </span>
                <span className="text-xs text-slate-500">• Canonical Lifecycle Passport</span>
              </div>
              <h2 className="text-2xl font-black text-slate-950 mt-1">
                My Garage: Vehicle Master Passport
              </h2>
            </div>

            <button
              onClick={() => setAddVehicleOpen(true)}
              className="px-4 py-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 text-amber-400 text-xs font-bold flex items-center gap-2 shadow-sm"
            >
              <Plus className="w-4 h-4" />
              <span>Add Vehicle via VIN / Plate</span>
            </button>
          </div>

          {/* Vehicle Selector Tabs */}
          <div className="flex gap-3 overflow-x-auto pb-1">
            {vehicles.map((v) => (
              <button
                key={v.id}
                onClick={() => setSelectedVehicle(v)}
                className={`p-3 rounded-2xl border text-left min-w-[240px] transition-all flex items-center gap-3 ${
                  selectedVehicle.id === v.id
                    ? "border-amber-400 bg-amber-50/60 shadow-sm"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="w-12 h-12 rounded-xl overflow-hidden bg-slate-100 shrink-0">
                  <img src={v.primaryImageUrl} alt={v.model} className="w-full h-full object-cover" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-black text-slate-900 truncate">
                    {v.year} {v.make} {v.model}
                  </div>
                  <div className="text-[11px] font-mono font-bold text-amber-700">
                    {v.registrationPlate}
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Detailed Passport Card */}
          <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm">
            <div className="flex flex-col lg:flex-row justify-between gap-6 pb-6 border-b border-slate-100">
              <div className="flex gap-5">
                <div className="w-28 h-28 rounded-2xl overflow-hidden bg-slate-100 shrink-0 border border-slate-200">
                  <img
                    src={selectedVehicle.primaryImageUrl}
                    alt={selectedVehicle.model}
                    className="w-full h-full object-cover"
                  />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-black bg-amber-400 text-slate-950 px-2 py-0.5 rounded">
                      {selectedVehicle.registrationPlate}
                    </span>
                    <span className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 font-bold px-2 py-0.5 rounded flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      VIN Verified
                    </span>
                  </div>
                  <h3 className="text-xl sm:text-2xl font-black text-slate-950 mt-1.5">
                    {selectedVehicle.year} {selectedVehicle.make} {selectedVehicle.model}
                  </h3>
                  <div className="text-xs text-slate-500 mt-0.5 font-medium">
                    {selectedVehicle.trim} • VIN: <span className="font-mono text-slate-800">{selectedVehicle.vin}</span>
                  </div>
                </div>
              </div>

              {/* Specs pill grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                  <div className="text-slate-500 flex items-center gap-1">
                    <Gauge className="w-3.5 h-3.5 text-amber-500" /> Odometer
                  </div>
                  <div className="text-base font-black text-slate-900 mt-1">
                    {selectedVehicle.currentOdometer.toLocaleString()} mi
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                  <div className="text-slate-500 flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5 text-amber-500" /> MOT Status
                  </div>
                  <div className="text-base font-black text-emerald-700 mt-1 flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" /> {selectedVehicle.motStatus}
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                  <div className="text-slate-500 flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5 text-amber-500" /> Safety Recalls
                  </div>
                  <div className="text-base font-black text-slate-900 mt-1">
                    {selectedVehicle.activeRecallsCount} Active
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                  <div className="text-slate-500 flex items-center gap-1">
                    <Car className="w-3.5 h-3.5 text-amber-500" /> Engine / Power
                  </div>
                  <div className="text-base font-black text-slate-900 mt-1">
                    {selectedVehicle.powerBhp} bhp
                  </div>
                </div>
              </div>
            </div>

            {/* Digital Glovebox: Verified Service Records */}
            <div className="mt-6">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-amber-500" />
                  Verified Digital Glovebox (Immutable Service Write-Back)
                </h4>
                <span className="text-[11px] text-slate-500">
                  Records authenticated via certified workshop work orders
                </span>
              </div>

              {selectedVehicle.serviceHistory.length > 0 ? (
                <div className="space-y-3">
                  {selectedVehicle.serviceHistory.map((s) => (
                    <div
                      key={s.id}
                      className="p-4 bg-slate-50 rounded-2xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-900">{s.serviceType}</span>
                          <span className="text-[10px] font-mono text-slate-500 bg-white px-2 py-0.5 rounded border">
                            {s.invoiceRef}
                          </span>
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          {s.workshopName} • {s.date} • Recorded at <strong>{s.mileage.toLocaleString()} mi</strong>
                        </div>
                        <p className="text-xs text-slate-600 mt-1">{s.notes}</p>
                      </div>

                      <div className="text-right shrink-0">
                        <div className="text-sm font-black text-slate-900">£{s.cost}</div>
                        <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
                          Write-Back Verified
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center bg-slate-50 rounded-2xl border border-dashed border-slate-300 text-xs text-slate-500">
                  No maintenance records logged for this vehicle yet. Book a certified workshop service to automatically build your digital passport.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab: Orders & Escrow (Doc 09, Doc 10) */}
      {activeTab === "orders" && (
        <div className="space-y-6">
          <div className="pb-4 border-b border-slate-200">
            <span className="text-[10px] font-black uppercase tracking-wider text-blue-700 bg-blue-100 px-2 py-0.5 rounded">
              Commercial Escrow & Orders
            </span>
            <h2 className="text-2xl font-black text-slate-950 mt-1">
              Active Orders & Escrow Holding Accounts
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Every marketplace transaction operates under double-entry escrow protection. Funds remain locked until delivery or vehicle handover token sign-off.
            </p>
          </div>

          <div className="space-y-4">
            {orders.map((ord) => (
              <div
                key={ord.id}
                className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-6"
              >
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="font-mono text-xs font-black bg-slate-900 text-amber-400 px-2.5 py-1 rounded-lg">
                      {ord.id}
                    </span>
                    <span className="text-xs text-slate-500">Placed {new Date(ord.placedAt).toLocaleDateString()}</span>
                    <span className="bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded ml-auto sm:ml-2">
                      {ord.orderState}
                    </span>
                    <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-2 py-0.5 rounded flex items-center gap-1">
                      <Lock className="w-3 h-3" />
                      {ord.escrowState}
                    </span>
                  </div>

                  <h3 className="text-base font-black text-slate-950">
                    {ord.items.map((i) => i.title).join(", ")}
                  </h3>
                  <div className="text-xs text-slate-500 mt-1">
                    Seller: <strong className="text-slate-800">{ord.items[0]?.sellerName}</strong>
                    {ord.trackingNumber && (
                      <span className="ml-3 text-blue-600 font-semibold">
                        Tracking: {ord.shippingCarrier} ({ord.trackingNumber})
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-600 bg-slate-50 p-2.5 rounded-xl border border-slate-200 mt-3">
                    <strong className="text-slate-900 font-bold">Escrow Condition:</strong> {ord.escrowReleaseConditions}
                  </p>
                </div>

                <div className="flex flex-col lg:items-end justify-between border-t lg:border-t-0 pt-4 lg:pt-0 border-slate-100">
                  <div className="text-xl font-black text-slate-950">
                    £{(ord.totalMinorAmount / 100).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-slate-500 mb-3">Escrow Protected (GBP)</div>

                  <button
                    onClick={() => setActiveHandoverModal(ord)}
                    className="px-4 py-2 bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-black rounded-xl flex items-center gap-2 shadow-sm transition-all"
                  >
                    <QrCode className="w-4 h-4" />
                    <span>View Handover QR Pass</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Guaranteed Fit Parts (Doc 06) */}
      {activeTab === "parts_fitment" && (
        <div className="space-y-6">
          <div className="pb-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <span className="text-[10px] font-black uppercase tracking-wider text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
                Confirmed Fitment Catalogue
              </span>
              <h2 className="text-2xl font-black text-slate-950 mt-1">
                Guaranteed Fit Parts for {selectedVehicle.year} {selectedVehicle.make} {selectedVehicle.model}
              </h2>
            </div>
            <span className="text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-xl flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" /> 100% Fitment Liability Covered
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {MOCK_CATALOG_PARTS.map((p) => (
              <div
                key={p.id}
                className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm flex flex-col justify-between"
              >
                <div>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    {p.brand} • MPN: {p.mpn}
                  </div>
                  <h4 className="text-sm font-bold text-slate-950 mt-1 line-clamp-2">{p.name}</h4>
                  <div className="mt-2 text-xs text-emerald-700 font-bold flex items-center gap-1 bg-emerald-50 px-2 py-1 rounded">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Guaranteed Fit
                  </div>
                  <div className="text-xs text-slate-500 mt-2">
                    {p.sellerCount} verified suppliers • {p.inStockQuantity} units in stock
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                  <div className="text-base font-black text-slate-950">£{p.price}</div>
                  <button
                    onClick={() => alert(`Added ${p.name} to cart!`)}
                    className="px-3 py-1.5 bg-amber-400 hover:bg-amber-500 text-slate-950 font-bold text-xs rounded-lg"
                  >
                    Add to Cart
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Service Bookings & Disputes */}
      {(activeTab === "service_bookings" || activeTab === "disputes") && (
        <div className="bg-white rounded-3xl border border-slate-200 p-8 text-center max-w-xl mx-auto space-y-4">
          <ShieldCheck className="w-12 h-12 text-amber-500 mx-auto" />
          <h3 className="text-lg font-black text-slate-950">
            {activeTab === "service_bookings" ? "Workshop Booking System" : "Disputes & Problem Resolution"}
          </h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            {activeTab === "service_bookings"
              ? "All your upcoming certified garage appointments, work order check-ins, and technician change-order authorizations are managed in this view."
              : "DriverXtra Buyer Protection guarantees 48-hour RMA labels and double-entry refund execution if goods do not arrive as described or fail fitment checks."}
          </p>
          <div className="inline-block text-[11px] font-mono text-slate-500 bg-slate-100 px-3 py-1 rounded-full">
            Platform Support: Certified Service Network
          </div>
        </div>
      )}

      {/* Handover Modal (Doc 09 & Doc 10) */}
      {activeHandoverModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 text-center space-y-4 border border-slate-200 shadow-2xl">
            <h4 className="text-base font-black text-slate-950">
              Digital Handover Pass
            </h4>
            <p className="text-xs text-slate-500">
              Order Ref: <strong className="font-mono text-slate-900">{activeHandoverModal.id}</strong>
            </p>

            <div className="p-4 bg-slate-950 rounded-2xl flex flex-col items-center">
              <div className="w-36 h-36 bg-white rounded-xl p-2 flex items-center justify-center">
                <QrCode className="w-32 h-32 text-slate-950" />
              </div>
              <div className="font-mono text-xs font-bold text-amber-400 mt-3 tracking-widest">
                {activeHandoverModal.handoverAuthToken}
              </div>
            </div>

            <p className="text-xs text-slate-600">
              Present this pass at physical collection. Escrow funds will only be disbursed once scanned and verified by the dealer.
            </p>

            <button
              onClick={() => setActiveHandoverModal(null)}
              className="w-full h-11 bg-slate-950 text-white text-xs font-bold rounded-xl"
            >
              Close Pass
            </button>
          </div>
        </div>
      )}

      {/* Add Vehicle Modal */}
      {addVehicleOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 border border-slate-200 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h4 className="text-base font-black text-slate-950 flex items-center gap-2">
                <Car className="w-4 h-4 text-amber-500" />
                Add Vehicle via VIN / Registration
              </h4>
              <button onClick={() => setAddVehicleOpen(false)} className="text-slate-400 hover:text-slate-600">✕</button>
            </div>

            <form onSubmit={handleResolveAndAdd} className="space-y-4 mt-4">
              <div>
                <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                  Registration Plate (UK)
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. KV22 XYZ"
                  value={newReg}
                  onChange={(e) => setNewReg(e.target.value)}
                  className="w-full h-11 px-3 border border-slate-300 rounded-xl text-sm font-bold uppercase"
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                  Or 17-Character VIN
                </label>
                <input
                  type="text"
                  placeholder="e.g. WBA3A5C50DF918231"
                  value={newVin}
                  onChange={(e) => setNewVin(e.target.value)}
                  className="w-full h-11 px-3 border border-slate-300 rounded-xl text-sm font-mono uppercase"
                />
              </div>

              <div className="p-3 bg-amber-50 rounded-xl text-xs text-amber-900 border border-amber-200">
                <strong className="font-bold">Vehicle Resolver:</strong> Decodes make, model, trim, and MOT status from authoritative vehicle registers.
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setAddVehicleOpen(false)}
                  className="px-4 py-2 text-xs font-bold border border-slate-300 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resolvingVin}
                  className="px-4 py-2 text-xs font-black bg-amber-400 hover:bg-amber-500 text-slate-950 rounded-xl flex items-center gap-1.5"
                >
                  {resolvingVin ? "Resolving VIN..." : "Resolve & Save to Garage"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
