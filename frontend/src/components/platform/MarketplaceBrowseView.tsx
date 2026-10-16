"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  VehicleMake,
  VehicleModel,
  PartCategory,
} from "@/lib/api/client";
import {
  Search,
  Car,
  Wrench,
  Filter,
  CheckCircle2,
  ShieldCheck,
  Eye,
  X,
  Gauge,
  Fuel,
  MapPin,
  PackageCheck,
} from "lucide-react";

export default function MarketplaceBrowseView() {
  const [activeTab, setActiveTab] = useState<"vehicles" | "parts">("vehicles");

  // Vehicles state
  const [vehicles, setVehicles] = useState<MarketplaceVehicleListing[]>([]);
  const [vehiclesLoading, setVehiclesLoading] = useState(false);
  const [vehicleSearch, setVehicleSearch] = useState("");
  const [selectedMake, setSelectedMake] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [fuelType, setFuelType] = useState("");
  const [transmission, setTransmission] = useState("");
  const [maxVehiclePrice, setMaxVehiclePrice] = useState("");
  const [selectedVehicle, setSelectedVehicle] = useState<MarketplaceVehicleListing | null>(null);

  // Parts state
  const [parts, setParts] = useState<MarketplacePartListing[]>([]);
  const [partsLoading, setPartsLoading] = useState(false);
  const [partSearch, setPartSearch] = useState("");
  const [partBrand, setPartBrand] = useState("");
  const [partMpn, setPartMpn] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [maxPartPrice, setMaxPartPrice] = useState("");
  const [selectedPart, setSelectedPart] = useState<MarketplacePartListing | null>(null);

  // Reference data
  const [makes, setMakes] = useState<VehicleMake[]>([]);
  const [models, setModels] = useState<VehicleModel[]>([]);
  const [categories, setCategories] = useState<PartCategory[]>([]);

  // Load makes and categories on mount
  useEffect(() => {
    api.catalogue.getMakes().then(setMakes).catch(console.error);
    api.catalogue.getCategories().then(setCategories).catch(console.error);
  }, []);

  // Update models when make changes
  useEffect(() => {
    if (!selectedMake) return;
    let ignore = false;
    api.catalogue.getModels(selectedMake).then((res) => {
      if (!ignore) setModels(res);
    }).catch(console.error);
    return () => {
      ignore = true;
    };
  }, [selectedMake]);

  // Fetch approved vehicles
  const fetchVehicles = useCallback(async () => {
    setVehiclesLoading(true);
    try {
      const params: Record<string, string> = {};
      if (vehicleSearch) params.search = vehicleSearch;
      if (selectedMake) params.make_id = selectedMake;
      if (selectedModel) params.model_id = selectedModel;
      if (fuelType) params.fuel_type = fuelType;
      if (transmission) params.transmission = transmission;
      if (maxVehiclePrice) params.price_max = maxVehiclePrice;

      const data = await api.marketplace.browseVehicles(params);
      setVehicles(data);
    } catch (err) {
      console.error("Failed to load approved vehicles", err);
    } finally {
      setVehiclesLoading(false);
    }
  }, [vehicleSearch, selectedMake, selectedModel, fuelType, transmission, maxVehiclePrice]);

  // Fetch approved parts
  const fetchParts = useCallback(async () => {
    setPartsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (partSearch) params.search = partSearch;
      if (partBrand) params.brand = partBrand;
      if (partMpn) params.mpn = partMpn;
      if (selectedCategory) params.category_id = selectedCategory;
      if (maxPartPrice) params.price_max = maxPartPrice;

      const data = await api.marketplace.browseParts(params);
      setParts(data);
    } catch (err) {
      console.error("Failed to load approved parts", err);
    } finally {
      setPartsLoading(false);
    }
  }, [partSearch, partBrand, partMpn, selectedCategory, maxPartPrice]);

  useEffect(() => {
    let ignore = false;
    const loadBrowse = async () => {
      try {
        if (activeTab === "vehicles") {
          const params: Record<string, string> = {};
          if (vehicleSearch) params.search = vehicleSearch;
          if (selectedMake) params.make_id = selectedMake;
          if (selectedModel) params.model_id = selectedModel;
          if (fuelType) params.fuel_type = fuelType;
          if (transmission) params.transmission = transmission;
          if (maxVehiclePrice) params.price_max = maxVehiclePrice;

          const data = await api.marketplace.browseVehicles(params);
          if (!ignore) setVehicles(data);
        } else {
          const params: Record<string, string> = {};
          if (partSearch) params.search = partSearch;
          if (partBrand) params.brand = partBrand;
          if (partMpn) params.mpn = partMpn;
          if (selectedCategory) params.category_id = selectedCategory;
          if (maxPartPrice) params.price_max = maxPartPrice;

          const data = await api.marketplace.browseParts(params);
          if (!ignore) setParts(data);
        }
      } catch (err) {
        if (!ignore) console.error("Failed to load browse items", err);
      }
    };
    loadBrowse();
    return () => {
      ignore = true;
    };
  }, [activeTab, vehicleSearch, selectedMake, selectedModel, fuelType, transmission, maxVehiclePrice, partSearch, partBrand, partMpn, selectedCategory, maxPartPrice]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 text-white flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-xs font-bold uppercase tracking-wider border border-amber-500/20">
              Verified Marketplace
            </span>
            <span className="text-xs text-slate-400">Buyer Browsing Experience</span>
          </div>
          <h2 className="text-2xl font-black text-white">Automotive Marketplace & Spare Parts</h2>
          <p className="text-xs text-slate-300 mt-1 max-w-xl">
            Browse confirmed vehicles for sale and verified OEM-compatible spare parts from authorized UK dealerships and accredited sellers.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex p-1 bg-slate-950/80 rounded-2xl border border-slate-800 self-start md:self-auto">
          <button
            onClick={() => setActiveTab("vehicles")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "vehicles"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Car className="w-4 h-4" />
            <span>Vehicles for Sale ({vehicles.length})</span>
          </button>
          <button
            onClick={() => setActiveTab("parts")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "parts"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Wrench className="w-4 h-4" />
            <span>Spare Parts ({parts.length})</span>
          </button>
        </div>
      </div>

      {/* =========================================================================
          TAB 1: VEHICLES BROWSE & SEARCH
      ========================================================================= */}
      {activeTab === "vehicles" && (
        <div className="space-y-6">
          {/* Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-3">
            <div className="flex flex-col md:flex-row items-center gap-3">
              <div className="relative flex-1 w-full">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by make, model, trim or keyword..."
                  value={vehicleSearch}
                  onChange={(e) => setVehicleSearch(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
                />
              </div>

              <select
                value={selectedMake}
                onChange={(e) => {
                  setSelectedMake(e.target.value);
                  setSelectedModel("");
                  setModels([]);
                }}
                className="w-full md:w-44 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              >
                <option value="">All Makes</option>
                {makes.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>

              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={!selectedMake}
                className="w-full md:w-44 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500 disabled:opacity-50"
              >
                <option value="">All Models</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>

              <select
                value={fuelType}
                onChange={(e) => setFuelType(e.target.value)}
                className="w-full md:w-36 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              >
                <option value="">Any Fuel</option>
                <option value="PETROL">Petrol</option>
                <option value="DIESEL">Diesel</option>
                <option value="HYBRID">Hybrid</option>
                <option value="EV">Electric</option>
              </select>

              <select
                value={transmission}
                onChange={(e) => setTransmission(e.target.value)}
                className="w-full md:w-36 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              >
                <option value="">Any Gearbox</option>
                <option value="AUTOMATIC">Automatic</option>
                <option value="MANUAL">Manual</option>
                <option value="DUAL_CLUTCH">Dual Clutch</option>
              </select>

              <input
                type="number"
                placeholder="Max Price (£)"
                value={maxVehiclePrice}
                onChange={(e) => setMaxVehiclePrice(e.target.value)}
                className="w-full md:w-32 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              />

              <button
                onClick={fetchVehicles}
                className="w-full md:w-auto px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800 transition-colors flex items-center justify-center gap-1.5"
              >
                <Filter className="w-3.5 h-3.5 text-amber-400" />
                <span>Filter</span>
              </button>
            </div>
          </div>

          {/* Vehicle Grid */}
          {vehiclesLoading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Scanning approved vehicle marketplace...</p>
            </div>
          ) : vehicles.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200">
              <Car className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-slate-900">No Approved Vehicles Match Your Filters</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                Try widening your price range, clearing specific filters, or checking back soon as verified sellers list new stock.
              </p>
              <button
                onClick={() => {
                  setVehicleSearch("");
                  setSelectedMake("");
                  setSelectedModel("");
                  setFuelType("");
                  setTransmission("");
                  setMaxVehiclePrice("");
                }}
                className="mt-4 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold rounded-xl transition-colors"
              >
                Reset All Filters
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {vehicles.map((v) => (
                <div
                  key={v.id}
                  className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
                >
                  <div>
                    {/* Image / Header Banner */}
                    <div className="relative h-44 bg-slate-950 flex items-center justify-center overflow-hidden">
                      {v.primary_image_url ? (
                        <img
                          src={v.primary_image_url}
                          alt={v.title}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="text-center p-4">
                          <Car className="w-12 h-12 text-slate-700 mx-auto mb-1" />
                          <span className="text-[10px] text-slate-500 font-medium">Verified Dealer Vehicle</span>
                        </div>
                      )}
                      <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/80 backdrop-blur-md text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Verified Approved</span>
                      </div>
                      <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-xl bg-slate-950/90 text-white font-black text-sm">
                        £{Number(v.price).toLocaleString()}
                      </div>
                    </div>

                    {/* Content */}
                    <div className="p-5 space-y-3">
                      <div>
                        <div className="text-[11px] font-bold text-amber-600 uppercase tracking-wider">
                          {v.year} · {v.make_name} {v.model_name}
                        </div>
                        <h4 className="text-sm font-black text-slate-900 line-clamp-1">{v.title}</h4>
                      </div>

                      <div className="grid grid-cols-3 gap-2 py-2 border-y border-slate-100 text-[11px]">
                        <div className="flex items-center gap-1 text-slate-600">
                          <Gauge className="w-3.5 h-3.5 text-slate-400" />
                          <span>{v.mileage ? v.mileage.toLocaleString() : "N/A"} mi</span>
                        </div>
                        <div className="flex items-center gap-1 text-slate-600">
                          <Fuel className="w-3.5 h-3.5 text-slate-400" />
                          <span className="capitalize">{v.fuel_type?.toLowerCase() || "Petrol"}</span>
                        </div>
                        <div className="flex items-center gap-1 text-slate-600">
                          <MapPin className="w-3.5 h-3.5 text-slate-400" />
                          <span className="truncate">{v.location_city || "UK"}</span>
                        </div>
                      </div>

                      {/* Privacy & Seller Tag */}
                      <div className="flex items-center justify-between text-[11px] text-slate-500">
                        <span>Seller: <strong className="text-slate-800">{v.organisation_name || v.seller_name || "Verified Trader"}</strong></span>
                        <span className="font-mono text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">
                          VIN: {v.masked_vin || "***********Verified"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Action */}
                  <div className="p-5 pt-0">
                    <button
                      onClick={() => setSelectedVehicle(v)}
                      className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>Inspect Vehicle Details</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 2: SPARE PARTS BROWSE & SEARCH
      ========================================================================= */}
      {activeTab === "parts" && (
        <div className="space-y-6">
          {/* Part Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-3">
            <div className="flex flex-col md:flex-row items-center gap-3">
              <div className="relative flex-1 w-full">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search part name, OEM reference, or keywords..."
                  value={partSearch}
                  onChange={(e) => setPartSearch(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
                />
              </div>

              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full md:w-52 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              >
                <option value="">All Categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>

              <input
                type="text"
                placeholder="Brand (e.g. Brembo)"
                value={partBrand}
                onChange={(e) => setPartBrand(e.target.value)}
                className="w-full md:w-36 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              />

              <input
                type="text"
                placeholder="MPN"
                value={partMpn}
                onChange={(e) => setPartMpn(e.target.value)}
                className="w-full md:w-32 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              />

              <input
                type="number"
                placeholder="Max Price (£)"
                value={maxPartPrice}
                onChange={(e) => setMaxPartPrice(e.target.value)}
                className="w-full md:w-32 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              />

              <button
                onClick={fetchParts}
                className="w-full md:w-auto px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800 transition-colors flex items-center justify-center gap-1.5"
              >
                <Filter className="w-3.5 h-3.5 text-amber-400" />
                <span>Filter</span>
              </button>
            </div>
          </div>

          {/* Parts Grid */}
          {partsLoading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Loading confirmed spare parts catalog...</p>
            </div>
          ) : parts.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200">
              <Wrench className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-slate-900">No Approved Spare Parts Match Your Query</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                No matching parts were found. Try searching by OEM part number or selecting a different category.
              </p>
              <button
                onClick={() => {
                  setPartSearch("");
                  setPartBrand("");
                  setPartMpn("");
                  setSelectedCategory("");
                  setMaxPartPrice("");
                }}
                className="mt-4 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold rounded-xl transition-colors"
              >
                Reset Parts Filter
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {parts.map((p) => (
                <div
                  key={p.id}
                  className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
                >
                  <div className="p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
                        {p.brand}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>In Stock ({p.stock_quantity})</span>
                      </span>
                    </div>

                    <div>
                      <h4 className="text-sm font-black text-slate-950 line-clamp-1">{p.name}</h4>
                      <p className="text-[11px] text-slate-500 font-mono mt-0.5">MPN: {p.mpn}</p>
                    </div>

                    <div className="p-3 bg-slate-50 rounded-2xl border border-slate-100 text-xs space-y-1">
                      <div className="flex items-center justify-between text-slate-600">
                        <span>Category:</span>
                        <strong className="text-slate-900">{p.category_name || "General"}</strong>
                      </div>
                      <div className="flex items-center justify-between text-slate-600">
                        <span>Condition:</span>
                        <strong className="text-slate-900">{p.condition}</strong>
                      </div>
                      {p.compatible_variants && p.compatible_variants.length > 0 && (
                        <div className="flex items-center justify-between text-slate-600">
                          <span>Verified Fitments:</span>
                          <span className="text-emerald-700 font-bold">
                            {p.compatible_variants.length} Variant(s)
                          </span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-baseline justify-between pt-1">
                      <span className="text-xs text-slate-500">Retail Price:</span>
                      <span className="text-lg font-black text-slate-950">
                        £{Number(p.price).toFixed(2)}
                      </span>
                    </div>
                  </div>

                  <div className="p-5 pt-0">
                    <button
                      onClick={() => setSelectedPart(p)}
                      className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>View Specifications & Fitment</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          MODAL: VEHICLE DETAIL INSPECTOR
      ========================================================================= */}
      {selectedVehicle && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  Approved Marketplace Vehicle
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">{selectedVehicle.title}</h3>
              </div>
              <button
                onClick={() => setSelectedVehicle(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {selectedVehicle.primary_image_url && (
              <div className="rounded-2xl overflow-hidden h-60 bg-slate-900">
                <img
                  src={selectedVehicle.primary_image_url}
                  alt={selectedVehicle.title}
                  className="w-full h-full object-cover"
                />
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Asking Price</span>
                <p className="font-black text-sm text-slate-950 mt-0.5">
                  £{Number(selectedVehicle.price).toLocaleString()}
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Year / Plate</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedVehicle.year}</p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Mileage</span>
                <p className="font-bold text-slate-900 mt-0.5">
                  {selectedVehicle.mileage.toLocaleString()} mi
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Transmission</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedVehicle.transmission}</p>
              </div>
            </div>

            {/* Privacy notice for identifiers */}
            <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 text-xs space-y-1.5">
              <div className="flex items-center gap-1.5 font-bold text-slate-800">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Protected Identifiers (Privacy & Security Standard)</span>
              </div>
              <div className="flex flex-wrap gap-4 text-slate-600 text-[11px]">
                <span>Masked VIN: <strong className="font-mono">{selectedVehicle.masked_vin}</strong></span>
                <span>Registration: <strong className="font-mono">{selectedVehicle.masked_registration}</strong></span>
                <span>Location: <strong>{selectedVehicle.location_city || "United Kingdom"}</strong></span>
              </div>
            </div>

            {selectedVehicle.description && (
              <div className="space-y-1 text-xs">
                <h5 className="font-bold text-slate-800">Seller Description</h5>
                <p className="text-slate-600 whitespace-pre-line leading-relaxed bg-slate-50 p-3.5 rounded-2xl border border-slate-100">
                  {selectedVehicle.description}
                </p>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedVehicle(null)}
                className="px-5 py-2.5 bg-slate-900 text-white text-xs font-bold rounded-xl"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: PART DETAIL INSPECTOR
      ========================================================================= */}
      {selectedPart && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  Confirmed Spare Part
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">{selectedPart.name}</h3>
                <p className="text-xs text-slate-500 font-mono">
                  {selectedPart.brand} · MPN: {selectedPart.mpn}
                </p>
              </div>
              <button
                onClick={() => setSelectedPart(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Retail Price</span>
                <p className="font-black text-base text-slate-950 mt-0.5">
                  £{Number(selectedPart.price).toFixed(2)}
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Stock Availability</span>
                <p className="font-bold text-emerald-700 mt-0.5">
                  {selectedPart.stock_quantity} Units Available
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Condition</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedPart.condition}</p>
              </div>
            </div>

            {selectedPart.oem_numbers && selectedPart.oem_numbers.length > 0 && (
              <div className="space-y-1 text-xs">
                <h5 className="font-bold text-slate-800">OEM Cross-Reference Numbers</h5>
                <div className="flex flex-wrap gap-2">
                  {selectedPart.oem_numbers.map((oem, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 bg-slate-100 text-slate-700 font-mono text-[11px] rounded-lg border border-slate-200"
                    >
                      {oem}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Fitment Evidence Confirmation */}
            <div className="space-y-2 text-xs">
              <h5 className="font-bold text-slate-800 flex items-center gap-1.5">
                <PackageCheck className="w-4 h-4 text-emerald-600" />
                <span>Verified Vehicle Compatibility</span>
              </h5>
              {selectedPart.compatible_variants && selectedPart.compatible_variants.length > 0 ? (
                <div className="p-3 bg-emerald-50/50 rounded-2xl border border-emerald-100 space-y-1.5">
                  {selectedPart.compatible_variants.map((v) => (
                    <div
                      key={v.id}
                      className="flex items-center justify-between text-[11px] text-slate-700"
                    >
                      <span>
                        {v.year} {v.make_name} {v.model_name} {v.name} ({v.engine_code || v.fuel_type})
                      </span>
                      <span className="font-bold text-emerald-700">Confirmed Fit</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 text-[11px] italic">
                  Universal application or manual fitment verification required.
                </p>
              )}
            </div>

            {selectedPart.description && (
              <div className="space-y-1 text-xs">
                <h5 className="font-bold text-slate-800">Technical Description</h5>
                <p className="text-slate-600 leading-relaxed bg-slate-50 p-3.5 rounded-2xl border border-slate-100">
                  {selectedPart.description}
                </p>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedPart(null)}
                className="px-5 py-2.5 bg-slate-900 text-white text-xs font-bold rounded-xl"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
