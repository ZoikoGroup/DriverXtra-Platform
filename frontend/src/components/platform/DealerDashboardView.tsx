"use client";

import React, { useState } from "react";
import { MOCK_DEALER_INVENTORY, InventoryItem } from "@/lib/mock-data/inventory";
import {
  RefreshCw,
  Plus,
  CheckCircle2,
  Lock
} from "lucide-react";

export default function DealerDashboardView({ activeTab }: { activeTab: string }) {
  const [inventory, setInventory] = useState<InventoryItem[]>(MOCK_DEALER_INVENTORY);
  const [syncingFeed, setSyncingFeed] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState("14 minutes ago");
  const [editPriceItem, setEditPriceItem] = useState<InventoryItem | null>(null);
  const [newPrice, setNewPrice] = useState("");

  // Create Listing Modal
  const [createListingOpen, setCreateListingOpen] = useState(false);
  const [wizardMake, setWizardMake] = useState("Audi");
  const [wizardModel, setWizardModel] = useState("A5 Sportback");
  const [wizardPrice, setWizardPrice] = useState("28500");
  const [wizardVin, setWizardVin] = useState("WAUZZZF53KA091823");

  const handleSyncDms = () => {
    setSyncingFeed(true);
    setTimeout(() => {
      setSyncingFeed(false);
      setLastSyncTime("Just now");
    }, 1200);
  };

  const handleSavePrice = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editPriceItem || !newPrice) return;
    const updated = inventory.map((item) =>
      item.id === editPriceItem.id ? { ...item, price: parseFloat(newPrice) } : item
    );
    setInventory(updated);
    setEditPriceItem(null);
    setNewPrice("");
  };

  const handleCreateListing = (e: React.FormEvent) => {
    e.preventDefault();
    const newItem: InventoryItem = {
      id: `inv_custom_${Date.now()}`,
      vehicleInstanceId: `veh_new_${Date.now()}`,
      title: `2023 ${wizardMake} ${wizardModel} S Line`,
      vin: wizardVin,
      registrationPlate: "LD23 XYZ",
      year: 2023,
      make: wizardMake,
      model: wizardModel,
      price: parseFloat(wizardPrice) || 28500,
      monthlyPcp: 395,
      costBasis: 25000,
      mileage: 14200,
      transmission: "S Tronic",
      fuel: "Mild Hybrid Petrol",
      listingStatus: "ACTIVE",
      inventoryStatus: "AVAILABLE",
      ingestionSource: "DIRECT_WIZARD",
      daysInStock: 0,
      leadCount: 0,
      escrowDepositHeld: 0,
      primaryImageUrl: "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=800&q=80",
      dealerOrganizationId: "org_dealer_0182"
    };
    setInventory([newItem, ...inventory]);
    setCreateListingOpen(false);
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
            Dealership Inventory & DMS Feeds
          </span>
        </div>
      </div>

      {/* Top Banner KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Active Stock
          </span>
          <div className="text-2xl font-black text-slate-950 mt-1 flex items-baseline justify-between">
            <span>{inventory.length} Vehicles</span>
            <span className="text-xs text-emerald-600 font-bold">+1 added</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Held in Escrow
          </span>
          <div className="text-2xl font-black text-amber-600 mt-1 flex items-baseline justify-between">
            <span>£84,200</span>
            <span className="text-xs text-slate-500">2 Handover Passes</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Cleared Balance
          </span>
          <div className="text-2xl font-black text-emerald-700 mt-1 flex items-baseline justify-between">
            <span>£142,650</span>
            <span className="text-xs bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded">
              Payout Ready
            </span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            DMS Feed Status
          </span>
          <div className="text-base font-black text-slate-950 mt-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-emerald-600 text-sm">
              <CheckCircle2 className="w-4 h-4 text-emerald-500" /> AutoSync Active
            </span>
            <span className="text-[11px] text-slate-400 font-medium">{lastSyncTime}</span>
          </div>
        </div>
      </div>

      {/* Main Table / View based on active tab */}
      {(activeTab === "inventory" || activeTab === "default") && (
        <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-6 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-wider text-amber-700 bg-amber-100 px-2 py-0.5 rounded">
                  Marketplace Inventory
                </span>
                <span className="text-xs text-slate-500">• Canonical Product & Offer Separation</span>
              </div>
              <h3 className="text-lg font-black text-slate-950 mt-1">
                Dealer Vehicle Inventory Register
              </h3>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleSyncDms}
                disabled={syncingFeed}
                className="px-4 py-2 border border-slate-300 rounded-xl text-xs font-bold text-slate-700 hover:bg-slate-50 flex items-center gap-2 transition-all"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${syncingFeed ? "animate-spin text-amber-500" : ""}`} />
                <span>{syncingFeed ? "Syncing DMS..." : "Sync DMS Feed"}</span>
              </button>

              <button
                onClick={() => setCreateListingOpen(true)}
                className="px-4 py-2 bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-black rounded-xl flex items-center gap-1.5 shadow-sm"
              >
                <Plus className="w-4 h-4" />
                <span>Create Listing Wizard</span>
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="py-3.5 px-4">Vehicle Details</th>
                  <th className="py-3.5 px-4">VIN Number</th>
                  <th className="py-3.5 px-4">Price</th>
                  <th className="py-3.5 px-4">Listing State</th>
                  <th className="py-3.5 px-4">Days in Stock</th>
                  <th className="py-3.5 px-4">Ingestion Feed</th>
                  <th className="py-3.5 px-4 text-right">Quick Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {inventory.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-slate-950">
                      <div className="flex items-center gap-3">
                        <img
                          src={item.primaryImageUrl}
                          alt={item.model}
                          className="w-10 h-10 rounded-lg object-cover bg-slate-100"
                        />
                        <div>
                          <div>{item.title}</div>
                          <div className="text-[11px] text-slate-400 font-normal">
                            {item.mileage.toLocaleString()} mi • {item.transmission}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500 text-[11px]">
                      {item.vin}
                    </td>
                    <td className="py-3.5 px-4 font-black text-slate-950 text-sm">
                      £{item.price.toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4">
                      {item.listingStatus === "ACTIVE" && (
                        <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-2 py-0.5 rounded">
                          ACTIVE (In Search)
                        </span>
                      )}
                      {item.listingStatus === "RESERVED" && (
                        <span className="bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded flex items-center gap-1 w-fit">
                          <Lock className="w-2.5 h-2.5" /> ESCROW HELD
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-slate-600">
                      {item.daysInStock} days
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 text-[11px]">
                      {item.ingestionSource}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => {
                          setEditPriceItem(item);
                          setNewPrice(item.price.toString());
                        }}
                        className="px-2.5 py-1 text-xs font-bold text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-lg border border-amber-200 transition-colors"
                      >
                        Adjust Price
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: DMS Feeds (Doc 16 & Doc 20) */}
      {activeTab === "feeds" && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100">
            <div>
              <h3 className="text-base font-black text-slate-950">
                Dealer Management System (DMS) Feeds
              </h3>
              <p className="text-xs text-slate-500">
                Automated inventory sync feeds mapping external dealer inventory into Canonical Vehicle Master schema.
              </p>
            </div>
            <button
              onClick={handleSyncDms}
              className="px-4 py-2 bg-slate-950 text-amber-400 font-bold text-xs rounded-xl"
            >
              Force Sync Now
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200">
              <div className="text-xs font-bold text-slate-500">Feed Format</div>
              <div className="text-base font-black text-slate-900 mt-1">CDK Global / Auto/Mate REST</div>
              <div className="text-xs text-emerald-600 mt-2 font-bold flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Ingestion Verified
              </div>
            </div>

            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200">
              <div className="text-xs font-bold text-slate-500">Last Batch Size</div>
              <div className="text-base font-black text-slate-900 mt-1">48 Units Processed</div>
              <div className="text-xs text-slate-500 mt-2">0 Schema Errors / 0 Quarantines</div>
            </div>

            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200">
              <div className="text-xs font-bold text-slate-500">Webhook Status</div>
              <div className="text-base font-black text-slate-900 mt-1">HMAC-SHA256 Active</div>
              <div className="text-xs text-emerald-600 mt-2 font-bold">100% Delivery SLA</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Escrow & Settlements (Doc 10) */}
      {activeTab === "escrow_payouts" && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-4 border-b border-slate-100">
            <h3 className="text-base font-black text-slate-950">
              Escrow Custody & Settlement Ledger
            </h3>
            <p className="text-xs text-slate-500">
              Authoritative financial state of dealer balances. Payout release is triggered atomically upon vehicle collection pass scan.
            </p>
          </div>

          <div className="p-6 bg-slate-950 text-white rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">
                Available Cleared Payout Balance
              </span>
              <div className="text-3xl font-black text-amber-400 mt-1">£142,650.00</div>
              <div className="text-xs text-slate-400 mt-1">Settlement Bank: Barclays Commercial UK (•••9102)</div>
            </div>

            <button
              onClick={() => alert("Payout request submitted successfully.")}
              className="px-5 py-3 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black text-xs rounded-xl shadow transition-all"
            >
              Request Bank Payout (£142,650)
            </button>
          </div>
        </div>
      )}

      {/* Price Edit Modal */}
      {editPriceItem && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 border border-slate-200 shadow-2xl">
            <h4 className="text-base font-black text-slate-950">
              Adjust Price for {editPriceItem.title}
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Listing ID: <span className="font-mono text-slate-800">{editPriceItem.id}</span>
            </p>

            <form onSubmit={handleSavePrice} className="space-y-4 mt-4">
              <div>
                <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                  New Retail Price (£)
                </label>
                <input
                  type="number"
                  value={newPrice}
                  onChange={(e) => setNewPrice(e.target.value)}
                  className="w-full h-11 px-3 border border-slate-300 rounded-xl text-lg font-black"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditPriceItem(null)}
                  className="px-4 py-2 text-xs font-bold border border-slate-300 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-black bg-amber-400 hover:bg-amber-500 text-slate-950 rounded-xl"
                >
                  Save & Publish Price
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Listing Drawer */}
      {createListingOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 border border-slate-200 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h4 className="text-base font-black text-slate-950 flex items-center gap-2">
                <Plus className="w-4 h-4 text-amber-500" />
                Create Vehicle Listing
              </h4>
              <button onClick={() => setCreateListingOpen(false)} className="text-slate-400">✕</button>
            </div>

            <form onSubmit={handleCreateListing} className="space-y-3 mt-4 text-xs">
              <div>
                <label className="block font-bold text-slate-600 mb-1">17-Char Vehicle VIN</label>
                <input
                  type="text"
                  value={wizardVin}
                  onChange={(e) => setWizardVin(e.target.value)}
                  className="w-full h-10 px-3 border border-slate-300 rounded-xl font-mono uppercase font-bold"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-600 mb-1">Make</label>
                  <input
                    type="text"
                    value={wizardMake}
                    onChange={(e) => setWizardMake(e.target.value)}
                    className="w-full h-10 px-3 border border-slate-300 rounded-xl font-bold"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-600 mb-1">Model</label>
                  <input
                    type="text"
                    value={wizardModel}
                    onChange={(e) => setWizardModel(e.target.value)}
                    className="w-full h-10 px-3 border border-slate-300 rounded-xl font-bold"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-600 mb-1">Asking Retail Price (£)</label>
                <input
                  type="number"
                  value={wizardPrice}
                  onChange={(e) => setWizardPrice(e.target.value)}
                  className="w-full h-10 px-3 border border-slate-300 rounded-xl font-black text-sm"
                />
              </div>

              <div className="p-3 bg-amber-50 rounded-xl text-amber-900 border border-amber-200">
                <strong className="font-bold">Listing Policy:</strong> Listing will evaluate mandatory legal disclosures and vehicle title verification before publication.
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCreateListingOpen(false)}
                  className="px-4 py-2 border border-slate-300 rounded-xl font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl"
                >
                  Submit for Publication
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
