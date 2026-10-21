"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  VehicleMake,
  VehicleModel,
  PartCategory,
  CataloguePartOffer,
  GarageVehicle,
  PartBrowseFacets,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
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
  Tag,
  AlertTriangle,
  XCircle,
  Info,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  RotateCcw,
} from "lucide-react";

export default function MarketplaceBrowseView() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"vehicles" | "parts">("vehicles");

  // Garage Vehicles State (Phase 3 Part C)
  const [garageVehicles, setGarageVehicles] = useState<GarageVehicle[]>([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>("");

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

  // Parts state (Phase 3 Part D)
  const [parts, setParts] = useState<MarketplacePartListing[]>([]);
  const [partsLoading, setPartsLoading] = useState(false);
  const [partsError, setPartsError] = useState<string | null>(null);
  const [partSearch, setPartSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [partBrand, setPartBrand] = useState("");
  const [partMpn, setPartMpn] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [maxPartPrice, setMaxPartPrice] = useState("");
  const [conditionFilter, setConditionFilter] = useState<string>("");
  const [inStockOnly, setInStockOnly] = useState<boolean>(false);
  const [fitsOnly, setFitsOnly] = useState<boolean>(false);
  const [sortOption, setSortOption] = useState<"newest" | "relevance" | "price_asc" | "price_desc">("newest");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [facets, setFacets] = useState<PartBrowseFacets | null>(null);
  const [selectedPart, setSelectedPart] = useState<MarketplacePartListing | null>(null);
  const [catalogueOffers, setCatalogueOffers] = useState<CataloguePartOffer[]>([]);
  const [offersLoading, setOffersLoading] = useState(false);

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

  // Load buyer garage vehicles when logged in (Phase 3 Part C)
  useEffect(() => {
    if (!user) return;
    let ignore = false;
    api.garage
      .listVehicles()
      .then((res) => {
        if (ignore) return;
        const active = (res || []).filter((v) => !v.is_archived);
        setGarageVehicles(active);
        // Default to primary vehicle or first active vehicle
        const primary = active.find((v) => v.is_primary) || active[0];
        if (primary) {
          setSelectedVehicleId(primary.id);
        }
      })
      .catch((err) => {
        console.error("Failed to load user garage vehicles for fitment", err);
      });
    return () => {
      ignore = true;
    };
  }, [user]);

  // Selected garage vehicle info
  const selectedGarageVehicle = garageVehicles.find((v) => v.id === selectedVehicleId) || null;
  const isVehicleUnlinked = Boolean(selectedGarageVehicle && !selectedGarageVehicle.vehicle_variant);
  const effectiveFitsOnly = Boolean(user && selectedVehicleId && !isVehicleUnlinked && fitsOnly);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(partSearch);
    }, 300);
    return () => clearTimeout(timer);
  }, [partSearch]);

  // Load parts whenever filters or pagination change (Phase 3 Part D)
  useEffect(() => {
    if (activeTab !== "parts") return;
    let ignore = false;

    const loadParts = async () => {
      try {
        const params: Record<string, string | number | boolean> = {
          page: currentPage,
          page_size: pageSize,
          sort: sortOption,
          include_facets: true,
        };
        if (debouncedSearch) params.search = debouncedSearch;
        if (partBrand) params.brand = partBrand;
        if (partMpn) params.mpn = partMpn;
        if (selectedCategory) params.category_id = selectedCategory;
        if (maxPartPrice) params.price_max = maxPartPrice;
        if (conditionFilter) params.condition = conditionFilter;
        if (inStockOnly) params.in_stock = true;
        if (selectedVehicleId) {
          params.fits_vehicle = selectedVehicleId;
          if (effectiveFitsOnly) {
            params.fits_only = true;
          }
        }

        const res = await api.marketplace.browsePartsPaginated(params);
        if (!ignore) {
          setParts(res.results || []);
          setTotalCount(res.count || 0);
          if (res.facets) {
            setFacets(res.facets);
          }
          setPartsError(null);
        }
      } catch (err: unknown) {
        if (!ignore) {
          console.error("Failed to load approved parts", err);
          const msg =
            err instanceof Error
              ? err.message
              : "Failed to load parts. Please verify your search and filter parameters.";
          setPartsError(msg);
          setParts([]);
          setTotalCount(0);
        }
      } finally {
        if (!ignore) {
          setPartsLoading(false);
        }
      }
    };

    loadParts();
    return () => {
      ignore = true;
    };
  }, [
    activeTab,
    debouncedSearch,
    partBrand,
    partMpn,
    selectedCategory,
    maxPartPrice,
    conditionFilter,
    inStockOnly,
    selectedVehicleId,
    effectiveFitsOnly,
    sortOption,
    currentPage,
    pageSize,
  ]);

  useEffect(() => {
    let ignore = false;
    const loadVehicles = async () => {
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
        }
      } catch (err) {
        if (!ignore) console.error("Failed to load browse vehicles", err);
      }
    };
    loadVehicles();
    return () => {
      ignore = true;
    };
  }, [
    activeTab,
    vehicleSearch,
    selectedMake,
    selectedModel,
    fuelType,
    transmission,
    maxVehiclePrice,
  ]);

  // Open part inspector & load other offers for linked catalogue part (Phase 3 Part B)
  const handleSelectPart = (part: MarketplacePartListing) => {
    setSelectedPart(part);
    if (selectedVehicleId) {
      api.marketplace
        .getPart(part.id, { fits_vehicle: selectedVehicleId })
        .then((detailed) => {
          setSelectedPart(detailed);
        })
        .catch(console.error);
    }
    if (part.catalogue_part) {
      setOffersLoading(true);
      api.marketplace
        .getCataloguePartOffers(part.catalogue_part)
        .then(setCatalogueOffers)
        .catch((err) => {
          console.error("Failed to load catalogue part offers", err);
          setCatalogueOffers([]);
        })
        .finally(() => setOffersLoading(false));
    } else {
      setCatalogueOffers([]);
    }
  };

  // Render buyer fitment badge (Phase 3 Part C)
  const renderFitmentBadge = (fitment?: { status: string; qualifications: string; source: string }) => {
    if (!fitment) return null;
    switch (fitment.status) {
      case "VERIFIED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            <span>Verified fit</span>
          </span>
        );
      case "CONDITIONAL":
        return (
          <span
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300"
            title={fitment.qualifications || "Fits with conditions"}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            <span>Fits with conditions</span>
            {fitment.qualifications && (
              <span className="text-[10px] font-normal italic opacity-90 truncate max-w-xs">
                ({fitment.qualifications})
              </span>
            )}
          </span>
        );
      case "SELLER_CLAIMED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-sky-100 text-sky-800 border border-sky-300">
            <Info className="w-3.5 h-3.5 text-sky-600" />
            <span>Seller says it fits (not verified)</span>
          </span>
        );
      case "CONFLICT":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            <span>Does not fit</span>
          </span>
        );
      case "UNKNOWN":
      default:
        return (
          <span
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-300"
            title={fitment.qualifications || "Fitment unknown"}
          >
            <HelpCircle className="w-3.5 h-3.5 text-slate-500" />
            <span>Fitment unknown</span>
            {fitment.qualifications && fitment.qualifications !== "none" && (
              <span className="text-[10px] font-normal italic opacity-80">
                ({fitment.qualifications})
              </span>
            )}
          </span>
        );
    }
  };

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
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "vehicles"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
              }`}
          >
            <Car className="w-4 h-4" />
            <span>Vehicles for Sale ({vehicles.length})</span>
          </button>
          <button
            onClick={() => setActiveTab("parts")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "parts"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
              }`}
          >
            <Wrench className="w-4 h-4" />
            <span>Spare Parts ({totalCount > 0 ? totalCount : parts.length})</span>
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
          {/* Buyer Vehicle Fitment Selector (Phase 3 Part C) & Fits-Only Toggle (Phase 3 Part D) */}
          {user && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 text-white space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                    <Car className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold text-white block">Vehicle Fitment Verification</span>
                    <span className="text-[11px] text-slate-400">
                      Select a vehicle from your garage to evaluate part compatibility.
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2.5">
                  <select
                    value={selectedVehicleId}
                    onChange={(e) => setSelectedVehicleId(e.target.value)}
                    className="px-3 py-2 text-xs bg-slate-950 border border-slate-700 text-white rounded-xl focus:outline-none focus:border-amber-500 max-w-xs"
                  >
                    <option value="">None (Browse all parts unannotated)</option>
                    {garageVehicles.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.year} {v.make} {v.model} {v.trim || ""} {v.registration_plate ? `(${v.registration_plate})` : ""}{v.is_primary ? " ★ Primary" : ""}
                      </option>
                    ))}
                  </select>

                  {/* "Only parts that fit my vehicle" Toggle (Phase 3 Part D) */}
                  <label
                    className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs select-none transition-all ${fitsOnly
                        ? "bg-amber-500/20 border-amber-500 text-amber-300 font-bold"
                        : "bg-slate-950/80 border-slate-700 text-slate-300 hover:border-slate-500"
                      } ${!selectedVehicleId || isVehicleUnlinked ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
                    title={
                      !selectedVehicleId
                        ? "Select a vehicle from your garage to filter by fitment"
                        : isVehicleUnlinked
                          ? "Link this vehicle to the catalogue to check fitment (this vehicle does not have a catalogue variant assigned)."
                          : "Filter results to only parts that fit this vehicle"
                    }
                  >
                    <input
                      type="checkbox"
                      id="fits-only-toggle"
                      disabled={!selectedVehicleId || isVehicleUnlinked}
                      checked={fitsOnly}
                      onChange={(e) => setFitsOnly(e.target.checked)}
                      className="w-3.5 h-3.5 rounded text-amber-500 focus:ring-amber-400 bg-slate-900 border-slate-600"
                    />
                    <span>Only parts that fit my vehicle</span>
                  </label>

                  {selectedVehicleId && (
                    <button
                      onClick={() => {
                        setSelectedVehicleId("");
                        setFitsOnly(false);
                      }}
                      className="px-2.5 py-2 text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-xl transition-colors"
                      title="Clear vehicle filter"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>

              {/* Notice when selected garage vehicle has no linked variant */}
              {isVehicleUnlinked && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-300 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>Link this vehicle to the catalogue to check fitment (this vehicle does not have a catalogue variant assigned).</span>
                </div>
              )}
            </div>
          )}

          {/* Part Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-3">
            <div className="flex flex-col md:flex-row items-center gap-3">
              <div className="relative flex-1 w-full">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search part name, MPN, OEM number, or keywords..."
                  value={partSearch}
                  onChange={(e) => setPartSearch(e.target.value)}
                  className="w-full pl-9 pr-8 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
                />
                {partSearch && (
                  <button
                    onClick={() => setPartSearch("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full md:w-44 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
              >
                <option value="">All Categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>

              {/* Deterministic Sort Dropdown */}
              <select
                value={sortOption}
                onChange={(e) => {
                  setSortOption(e.target.value as "newest" | "relevance" | "price_asc" | "price_desc");
                  setCurrentPage(1);
                }}
                className="w-full md:w-44 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500 font-medium text-slate-800"
              >
                <option value="newest">Sort: Newest First</option>
                <option value="relevance">Sort: Relevance</option>
                <option value="price_asc">Sort: Price: Low to High</option>
                <option value="price_desc">Sort: Price: High to Low</option>
              </select>

              <button
                onClick={() => {
                  setPartSearch("");
                  setPartBrand("");
                  setPartMpn("");
                  setSelectedCategory("");
                  setMaxPartPrice("");
                  setConditionFilter("");
                  setInStockOnly(false);
                  setFitsOnly(false);
                  setSortOption("newest");
                }}
                className="w-full md:w-auto px-3 py-2 text-xs text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors flex items-center justify-center gap-1.5 font-medium"
                title="Reset all filters"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset</span>
              </button>
            </div>

            {/* Quick Secondary Filters: Condition, In-Stock, Brand, Price */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-slate-400 font-medium text-[11px] mr-1">Condition:</span>
                {[
                  { label: "All", value: "" },
                  { label: "New", value: "NEW" },
                  { label: "Used", value: "USED" },
                  { label: "Refurbished", value: "REFURBISHED" },
                ].map((c) => (
                  <button
                    key={c.value}
                    onClick={() => setConditionFilter(c.value)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${conditionFilter === c.value
                        ? "bg-slate-900 text-white shadow-sm"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                  >
                    {c.label}
                  </button>
                ))}

                <label className="flex items-center gap-1.5 ml-3 cursor-pointer select-none text-slate-700 font-medium">
                  <input
                    type="checkbox"
                    checked={inStockOnly}
                    onChange={(e) => setInStockOnly(e.target.checked)}
                    className="w-3.5 h-3.5 rounded text-amber-500 focus:ring-amber-400"
                  />
                  <span>In Stock Only</span>
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Filter Brand"
                  value={partBrand}
                  onChange={(e) => setPartBrand(e.target.value)}
                  className="w-28 px-2.5 py-1 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-amber-500"
                />
                <input
                  type="number"
                  placeholder="Max £"
                  value={maxPartPrice}
                  onChange={(e) => setMaxPartPrice(e.target.value)}
                  className="w-20 px-2.5 py-1 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>
          </div>

          {/* Main Layout: Facet Sidebar + Results Content Area */}
          <div className="flex flex-col lg:flex-row gap-6 items-start">
            {/* Facet Sidebar (Phase 3 Part D) */}
            <aside className="w-full lg:w-64 shrink-0 bg-white rounded-2xl border border-slate-200 p-4 shadow-sm space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="w-4 h-4 text-amber-500" />
                  <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">Filter Facets</span>
                </div>
                {(selectedCategory || partBrand || conditionFilter || inStockOnly || fitsOnly) && (
                  <button
                    onClick={() => {
                      setSelectedCategory("");
                      setPartBrand("");
                      setConditionFilter("");
                      setInStockOnly(false);
                      setFitsOnly(false);
                    }}
                    className="text-[11px] text-amber-600 hover:text-amber-700 font-semibold"
                  >
                    Clear All
                  </button>
                )}
              </div>

              {/* Categories Facet */}
              <div className="space-y-2">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Category</span>
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {facets?.categories && facets.categories.length > 0 ? (
                    facets.categories.map((cat) => {
                      const isSelected = selectedCategory === cat.id;
                      return (
                        <button
                          key={cat.id}
                          onClick={() => setSelectedCategory(isSelected ? "" : cat.id)}
                          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs transition-colors text-left ${isSelected
                              ? "bg-amber-500/10 text-amber-900 font-bold border border-amber-300"
                              : "text-slate-600 hover:bg-slate-50"
                            }`}
                        >
                          <span className="truncate mr-2">{cat.name}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${isSelected ? "bg-amber-500 text-slate-950 font-bold" : "bg-slate-100 text-slate-500"
                            }`}>
                            {cat.count}
                          </span>
                        </button>
                      );
                    })
                  ) : (
                    <span className="text-xs text-slate-400 italic">No category facets</span>
                  )}
                </div>
              </div>

              {/* Brands Facet */}
              <div className="space-y-2 pt-3 border-t border-slate-100">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Brand</span>
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {(() => {
                    const brandList: { brand: string; count: number }[] = Array.isArray(facets?.brands)
                      ? (facets.brands as unknown[]).flatMap((item) => {
                        if (item && typeof item === "object") {
                          const b = item as Record<string, unknown>;
                          if ("brand" in b && b.brand) {
                            return [{ brand: String(b.brand), count: Number(b.count || 0) }];
                          }
                        }
                        return [];
                      })
                      : facets?.brands && typeof facets.brands === "object"
                        ? Object.entries(facets.brands).flatMap(([brandKey, val]) => {
                          if (val && typeof val === "object" && val !== null) {
                            const valObj = val as Record<string, unknown>;
                            const bName = typeof valObj.brand === "string" ? valObj.brand : brandKey;
                            const bCount = Number(valObj.count || 0);
                            return [{ brand: bName, count: bCount }];
                          }
                          return [{ brand: brandKey, count: Number(val || 0) }];
                        })
                        : [];

                    if (brandList.length === 0) {
                      return <span className="text-xs text-slate-400 italic">No brand facets</span>;
                    }

                    return brandList.map(({ brand: brandName, count }) => {
                      const isSelected = partBrand.toLowerCase() === brandName.toLowerCase();
                      return (
                        <button
                          key={brandName}
                          onClick={() => {
                            setPartBrand(isSelected ? "" : brandName);
                            setCurrentPage(1);
                          }}
                          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs transition-colors text-left ${isSelected
                              ? "bg-amber-500/10 text-amber-900 font-bold border border-amber-300"
                              : "text-slate-600 hover:bg-slate-50"
                            }`}
                        >
                          <span className="truncate mr-2">{brandName}</span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded-full ${isSelected
                                ? "bg-amber-500 text-slate-950 font-bold"
                                : "bg-slate-100 text-slate-500"
                              }`}
                          >
                            {count}
                          </span>
                        </button>
                      );
                    });
                  })()}
                </div>
              </div>

              {/* Condition Facet */}
              <div className="space-y-2 pt-3 border-t border-slate-100">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Condition</span>
                <div className="space-y-1">
                  {(() => {
                    const conditionList: { condition: string; count: number }[] = Array.isArray(facets?.conditions)
                      ? (facets.conditions as unknown[]).flatMap((item) => {
                        if (item && typeof item === "object") {
                          const c = item as Record<string, unknown>;
                          if ("condition" in c && c.condition) {
                            return [{ condition: String(c.condition), count: Number(c.count || 0) }];
                          }
                        }
                        return [];
                      })
                      : facets?.conditions && typeof facets.conditions === "object"
                        ? Object.entries(facets.conditions).flatMap(([condKey, val]) => {
                          if (val && typeof val === "object" && val !== null) {
                            const valObj = val as Record<string, unknown>;
                            const cName = typeof valObj.condition === "string" ? valObj.condition : condKey;
                            const cCount = Number(valObj.count || 0);
                            return [{ condition: cName, count: cCount }];
                          }
                          return [{ condition: condKey, count: Number(val || 0) }];
                        })
                        : [];

                    if (conditionList.length === 0) {
                      return <span className="text-xs text-slate-400 italic">No condition facets</span>;
                    }

                    return conditionList.map(({ condition: condName, count }) => {
                      const isSelected = conditionFilter.toUpperCase() === condName.toUpperCase();
                      return (
                        <button
                          key={condName}
                          onClick={() => {
                            setConditionFilter(isSelected ? "" : condName);
                            setCurrentPage(1);
                          }}
                          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs transition-colors text-left ${isSelected
                              ? "bg-amber-500/10 text-amber-900 font-bold border border-amber-300"
                              : "text-slate-600 hover:bg-slate-50"
                            }`}
                        >
                          <span className="capitalize">{condName.toLowerCase()}</span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded-full ${isSelected
                                ? "bg-amber-500 text-slate-950 font-bold"
                                : "bg-slate-100 text-slate-500"
                              }`}
                          >
                            {count}
                          </span>
                        </button>
                      );
                    });
                  })()}
                </div>
              </div>
            </aside>

            {/* Results Grid & Pagination Area */}
            <div className="flex-1 w-full space-y-4">
              {/* Backend Error Banner */}
              {partsError && (
                <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl flex items-start gap-3 text-rose-800 text-xs shadow-sm">
                  <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <div className="font-bold">Error loading spare parts</div>
                    <div>{partsError}</div>
                  </div>
                </div>
              )}

              {/* Results Header / Active Filters Summary */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-1">
                <div className="text-xs text-slate-500">
                  Showing <strong className="text-slate-900">{parts.length}</strong> of{" "}
                  <strong className="text-slate-900">{totalCount}</strong> spare parts
                  {debouncedSearch && <span> for &ldquo;{debouncedSearch}&rdquo;</span>}
                </div>

                {/* Page Size Selector */}
                <div className="flex items-center gap-2 text-xs text-slate-500 self-end sm:self-auto">
                  <span>Show:</span>
                  <select
                    value={pageSize}
                    onChange={(e) => setPageSize(Number(e.target.value))}
                    className="px-2 py-1 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:border-amber-500 text-slate-700 font-medium"
                  >
                    <option value={10}>10 per page</option>
                    <option value={20}>20 per page</option>
                    <option value={50}>50 per page</option>
                  </select>
                </div>
              </div>

              {/* Active Filter Badges */}
              {(selectedCategory || partBrand || conditionFilter || inStockOnly || fitsOnly) && (
                <div className="flex flex-wrap items-center gap-1.5 px-1">
                  {selectedCategory && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] bg-slate-100 text-slate-700 border border-slate-200">
                      <span>Category: {categories.find((c) => c.id === selectedCategory)?.name || selectedCategory}</span>
                      <button onClick={() => setSelectedCategory("")} className="hover:text-rose-600">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )}
                  {partBrand && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] bg-slate-100 text-slate-700 border border-slate-200">
                      <span>Brand: {partBrand}</span>
                      <button onClick={() => setPartBrand("")} className="hover:text-rose-600">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )}
                  {conditionFilter && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] bg-slate-100 text-slate-700 border border-slate-200">
                      <span>Condition: {conditionFilter}</span>
                      <button onClick={() => setConditionFilter("")} className="hover:text-rose-600">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )}
                  {inStockOnly && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] bg-emerald-50 text-emerald-800 border border-emerald-200">
                      <span>In Stock Only</span>
                      <button onClick={() => setInStockOnly(false)} className="hover:text-rose-600">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )}
                  {fitsOnly && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] bg-amber-50 text-amber-800 border border-amber-300">
                      <span>Fits My Vehicle Only</span>
                      <button onClick={() => setFitsOnly(false)} className="hover:text-rose-600">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )}
                </div>
              )}

              {/* Parts Grid or Loading/Empty */}
              {partsLoading ? (
                <div className="py-20 text-center bg-white rounded-3xl border border-slate-200">
                  <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                  <p className="text-xs text-slate-500 font-medium">Loading confirmed spare parts catalog...</p>
                </div>
              ) : parts.length === 0 ? (
                <div className="bg-white rounded-3xl p-12 text-center border border-slate-200">
                  <Wrench className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <h3 className="text-base font-bold text-slate-900">No parts match your filters</h3>
                  <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                    Try broadening your search term, clearing facet filters, or disabling the fitment filter.
                  </p>
                  <button
                    onClick={() => {
                      setPartSearch("");
                      setPartBrand("");
                      setPartMpn("");
                      setSelectedCategory("");
                      setMaxPartPrice("");
                      setConditionFilter("");
                      setInStockOnly(false);
                      setFitsOnly(false);
                    }}
                    className="mt-4 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold rounded-xl transition-colors"
                  >
                    Reset Filters
                  </button>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-5">
                    {parts.map((p) => (
                      <div
                        key={p.id}
                        className={`bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col justify-between ${p.stock_quantity === 0 || p.availability === "OUT_OF_STOCK" ? "opacity-85" : ""
                          }`}
                      >
                        <div className="p-5 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
                              {p.brand}
                            </span>
                            <div className="flex items-center gap-1.5">
                              {p.fitment && renderFitmentBadge(p.fitment)}
                              {p.availability === "OUT_OF_STOCK" || p.stock_quantity === 0 ? (
                                <span className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[10px] font-bold border border-rose-200 flex items-center gap-1">
                                  <X className="w-3 h-3" />
                                  <span>Out of Stock</span>
                                </span>
                              ) : p.availability === "LOW_STOCK" || p.stock_quantity <= (p.low_stock_threshold ?? 3) ? (
                                <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200 flex items-center gap-1">
                                  <PackageCheck className="w-3 h-3" />
                                  <span>Low Stock ({p.stock_quantity} left)</span>
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" />
                                  <span>In Stock ({p.stock_quantity})</span>
                                </span>
                              )}
                            </div>
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
                            <div className="flex items-baseline gap-1.5">
                              {p.compare_at_price && Number(p.compare_at_price) > Number(p.price) && (
                                <span className="text-xs text-slate-400 line-through">
                                  £{Number(p.compare_at_price).toFixed(2)}
                                </span>
                              )}
                              <span className="text-lg font-black text-slate-950">
                                £{Number(p.price).toFixed(2)}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="p-5 pt-0 space-y-2">
                          <button
                            onClick={() => handleSelectPart(p)}
                            className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5"
                          >
                            <Eye className="w-3.5 h-3.5 text-amber-400" />
                            <span>View Specifications & Fitment</span>
                          </button>
                          <button
                            disabled={p.stock_quantity === 0 || p.availability === "OUT_OF_STOCK"}
                            className={`w-full py-2 text-xs font-bold rounded-xl transition-all flex items-center justify-center gap-1.5 ${p.stock_quantity === 0 || p.availability === "OUT_OF_STOCK"
                                ? "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                                : "bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-sm"
                              }`}
                          >
                            <span>
                              {p.stock_quantity === 0 || p.availability === "OUT_OF_STOCK"
                                ? "Out of Stock · Unavailable to Purchase"
                                : "Add to Basket"}
                            </span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Pagination Controls (Phase 3 Part D) */}
                  <div className="bg-white rounded-2xl border border-slate-200 p-4 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-sm">
                    <div className="text-xs text-slate-500">
                      Page <strong className="text-slate-800">{currentPage}</strong> of{" "}
                      <strong className="text-slate-800">{Math.max(1, Math.ceil(totalCount / pageSize))}</strong> (
                      {totalCount} total listings)
                    </div>

                    <div className="flex items-center gap-1.5">
                      <button
                        disabled={currentPage <= 1}
                        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1 border ${currentPage <= 1
                            ? "bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed"
                            : "bg-white hover:bg-slate-50 text-slate-700 border-slate-300 shadow-sm"
                          }`}
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                        <span>Previous</span>
                      </button>

                      {/* Page Numbers */}
                      {Array.from({ length: Math.min(5, Math.max(1, Math.ceil(totalCount / pageSize))) }, (_, i) => {
                        const pageNum = i + 1;
                        return (
                          <button
                            key={pageNum}
                            onClick={() => setCurrentPage(pageNum)}
                            className={`w-8 h-8 rounded-xl text-xs font-bold transition-all ${currentPage === pageNum
                                ? "bg-amber-500 text-slate-950 shadow-sm"
                                : "bg-white hover:bg-slate-50 text-slate-700 border border-slate-200"
                              }`}
                          >
                            {pageNum}
                          </button>
                        );
                      })}

                      <button
                        disabled={currentPage >= Math.max(1, Math.ceil(totalCount / pageSize))}
                        onClick={() =>
                          setCurrentPage((prev) =>
                            Math.min(Math.max(1, Math.ceil(totalCount / pageSize)), prev + 1)
                          )
                        }
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1 border ${currentPage >= Math.max(1, Math.ceil(totalCount / pageSize))
                            ? "bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed"
                            : "bg-white hover:bg-slate-50 text-slate-700 border-slate-300 shadow-sm"
                          }`}
                      >
                        <span>Next</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
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
                <div className="flex items-baseline gap-1.5 mt-0.5">
                  {selectedPart.compare_at_price && Number(selectedPart.compare_at_price) > Number(selectedPart.price) && (
                    <span className="text-xs text-slate-400 line-through">
                      £{Number(selectedPart.compare_at_price).toFixed(2)}
                    </span>
                  )}
                  <p className="font-black text-base text-slate-950">
                    £{Number(selectedPart.price).toFixed(2)}
                  </p>
                </div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Stock Availability</span>
                <p
                  className={`font-bold mt-0.5 ${selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"
                      ? "text-rose-600"
                      : selectedPart.stock_quantity <= (selectedPart.low_stock_threshold ?? 3)
                        ? "text-amber-600"
                        : "text-emerald-700"
                    }`}
                >
                  {selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"
                    ? "Out of Stock (Unavailable)"
                    : `${selectedPart.stock_quantity} Units Available`}
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Condition</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedPart.condition}</p>
              </div>
            </div>

            {/* Buyer Vehicle Fitment Verification (Phase 3 Part C) */}
            {selectedGarageVehicle && (
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Car className="w-4 h-4 text-amber-600" />
                    <span className="font-bold text-slate-900">
                      Evaluated for: {selectedGarageVehicle.year} {selectedGarageVehicle.make} {selectedGarageVehicle.model} {selectedGarageVehicle.trim || ""}
                      {selectedGarageVehicle.registration_plate ? ` (${selectedGarageVehicle.registration_plate})` : ""}
                    </span>
                  </div>
                  {renderFitmentBadge(selectedPart.fitment)}
                </div>

                {isVehicleUnlinked ? (
                  <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                    <span>Link this vehicle to the catalogue to check fitment</span>
                  </div>
                ) : (
                  selectedPart.fitment?.qualifications && selectedPart.fitment.qualifications !== "none" && (
                    <div className="p-2.5 bg-amber-50/70 border border-amber-200 rounded-xl text-[11px] text-amber-900">
                      <span className="font-bold block mb-0.5">Fitment Conditions / Catalogue Notes:</span>
                      <span>{selectedPart.fitment.qualifications}</span>
                    </div>
                  )
                )}
              </div>
            )}

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

            {/* Other Offers Section (Phase 3 Part B) */}
            {selectedPart.catalogue_part && (
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <h5 className="font-bold text-slate-800 flex items-center gap-1.5">
                    <Tag className="w-4 h-4 text-amber-500" />
                    <span>Other Offers for this Part</span>
                  </h5>
                  {offersLoading && (
                    <span className="text-[10px] text-slate-400">Checking catalogue offers...</span>
                  )}
                </div>

                {offersLoading ? (
                  <div className="p-4 text-center text-slate-400 text-xs">
                    Loading competitive seller offers...
                  </div>
                ) : catalogueOffers.filter((o) => o.id !== selectedPart.id).length === 0 ? (
                  <div className="p-3 bg-slate-50 rounded-2xl border border-slate-100 text-slate-500 text-[11px] italic">
                    No other verified seller offers currently available for this catalogue part.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {catalogueOffers
                      .filter((o) => o.id !== selectedPart.id)
                      .map((offer) => (
                        <div
                          key={offer.id}
                          className="p-3 bg-slate-50 hover:bg-slate-100/80 rounded-2xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors"
                        >
                          <div className="space-y-0.5">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-slate-900 text-xs">
                                {offer.organisation_name || offer.seller_name}
                              </span>
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200 text-slate-700">
                                {offer.condition}
                              </span>
                              {offer.availability === "OUT_OF_STOCK" || offer.stock_quantity === 0 ? (
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                                  Out of Stock (Unavailable)
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                  In Stock
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-500">
                              Seller: {offer.seller_name} {offer.organisation_name ? `(${offer.organisation_name})` : ""}
                            </p>
                          </div>

                          <div className="text-right flex sm:flex-col items-center sm:items-end justify-between sm:justify-center">
                            <div className="flex items-baseline gap-1.5">
                              {offer.compare_at_price && Number(offer.compare_at_price) > Number(offer.price) && (
                                <span className="text-xs text-slate-400 line-through font-mono">
                                  £{Number(offer.compare_at_price).toFixed(2)}
                                </span>
                              )}
                              <span className="text-sm font-black text-slate-950 font-mono">
                                £{Number(offer.price).toFixed(2)}
                              </span>
                            </div>
                            {offer.availability === "OUT_OF_STOCK" || offer.stock_quantity === 0 ? (
                              <span className="text-[10px] text-rose-600 font-bold mt-0.5">
                                Unavailable
                              </span>
                            ) : (
                              <span className="text-[10px] text-emerald-700 font-bold mt-0.5">
                                Available to Order
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
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

            <div className="pt-2 flex items-center justify-end gap-2">
              <button
                disabled={selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"}
                className={`px-5 py-2.5 text-xs font-bold rounded-xl transition-all ${selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"
                    ? "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                    : "bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-sm"
                  }`}
              >
                {selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"
                  ? "Out of Stock · Unavailable"
                  : "Add to Basket"}
              </button>
              <button
                onClick={() => setSelectedPart(null)}
                className="px-5 py-2.5 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800"
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
