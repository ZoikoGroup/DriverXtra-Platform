"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  resolveMediaUrl,
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
  Heart,
  ImageIcon,
  Building2,
  MessageSquare,
  Phone,
  MessageCircle,
  Send,
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
  const [selectedVehicleImageIdx, setSelectedVehicleImageIdx] = useState<number>(0);
  const [selectedPartImageIdx, setSelectedPartImageIdx] = useState<number>(0);

  // Vehicle Enquiry Modal State
  const [enquiryVehicle, setEnquiryVehicle] = useState<MarketplaceVehicleListing | null>(null);
  const [enquiryMessage, setEnquiryMessage] = useState<string>("");
  const [enquiryBuyerPhone, setEnquiryBuyerPhone] = useState<string>("");
  const [enquirySubmitting, setEnquirySubmitting] = useState<boolean>(false);
  const [enquirySuccess, setEnquirySuccess] = useState<string | null>(null);
  const [enquiryError, setEnquiryError] = useState<string | null>(null);

  // Favourites state
  const [favouriteVehicleIds, setFavouriteVehicleIds] = useState<Set<string>>(new Set());
  const [favouritePartIds, setFavouritePartIds] = useState<Set<string>>(new Set());
  const [favouriteLoading, setFavouriteLoading] = useState<Record<string, boolean>>({});
  const [favouritePartLoading, setFavouritePartLoading] = useState<Record<string, boolean>>({});
  const [favouriteError, setFavouriteError] = useState<string | null>(null);

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

  const handleOpenEnquiryModal = (vehicle: MarketplaceVehicleListing) => {
    setEnquiryVehicle(vehicle);
    setEnquiryMessage(
      "Hello, I am interested in your listed vehicle. Could you please share more details about its condition, availability and final price?"
    );
    setEnquiryBuyerPhone(user?.phone_number || "");
    setEnquirySuccess(null);
    setEnquiryError(null);
  };

  const handleSendEnquiry = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enquiryVehicle) return;
    if (!user) {
      setEnquiryError("Please log in to your DriverXtra account to send an enquiry to the seller.");
      return;
    }
    if (enquiryMessage.trim().length < 10) {
      setEnquiryError("Enquiry message must be at least 10 characters long.");
      return;
    }

    setEnquirySubmitting(true);
    setEnquiryError(null);
    try {
      const result = await api.marketplace.enquireVehicle(enquiryVehicle.id, {
        message: enquiryMessage.trim(),
        buyer_phone: enquiryBuyerPhone.trim(),
      });
      setEnquirySuccess(
        `Your enquiry has been sent directly to ${
          enquiryVehicle.seller_info?.name || enquiryVehicle.seller_name || "the seller"
        }! Reference: #${result.id.slice(0, 8)}`
      );
        } catch (err: unknown) {
      const error = err as {
        details?: { detail?: unknown };
        message?: string;
      };

      const msg =
        error.details?.detail ??
        error.message ??
        "Failed to submit enquiry. Please try again.";

      setEnquiryError(
        typeof msg === "string" ? msg : JSON.stringify(msg)
      );
    } finally {
      setEnquirySubmitting(false);
    }
  };

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

  // Load buyer favourites when user is logged in
  useEffect(() => {
    if (!user) {
      return;
    }
    let ignore = false;
    api.marketplace
      .listFavourites()
      .then((favs) => {
        if (!ignore) {
          setFavouriteVehicleIds(new Set(favs.map((f) => f.vehicle_id)));
        }
      })
      .catch((err: unknown) => {
        console.error("Failed to load buyer vehicle favourites", err);
      });

    api.marketplace
      .listPartFavourites()
      .then((favs) => {
        if (!ignore) {
          setFavouritePartIds(new Set(favs.map((f) => f.part_id)));
        }
      })
      .catch((err: unknown) => {
        console.error("Failed to load buyer spare part favourites", err);
      });

    return () => {
      ignore = true;
    };
  }, [user]);

  const handleToggleFavourite = async (e: React.MouseEvent, vehicleId: string) => {
    e.stopPropagation();
    if (!user) return;
    if (favouriteLoading[vehicleId]) return;

    setFavouriteLoading((prev) => ({ ...prev, [vehicleId]: true }));
    setFavouriteError(null);
    const isFav = favouriteVehicleIds.has(vehicleId);

    try {
      if (isFav) {
        await api.marketplace.removeFavourite(vehicleId);
        setFavouriteVehicleIds((prev) => {
          const next = new Set(prev);
          next.delete(vehicleId);
          return next;
        });
      } else {
        await api.marketplace.addFavourite(vehicleId);
        setFavouriteVehicleIds((prev) => {
          const next = new Set(prev);
          next.add(vehicleId);
          return next;
        });
      }
    } catch (err: unknown) {
      console.error("Failed to toggle favourite vehicle", err);
      const msg = err instanceof Error ? err.message : "Failed to update favourite vehicle.";
      setFavouriteError(msg);
    } finally {
      setFavouriteLoading((prev) => ({ ...prev, [vehicleId]: false }));
    }
  };

  const handleTogglePartFavourite = async (e: React.MouseEvent, partId: string) => {
    e.stopPropagation();
    if (!user) return;
    if (favouritePartLoading[partId]) return;

    setFavouritePartLoading((prev) => ({ ...prev, [partId]: true }));
    setFavouriteError(null);
    const isFav = favouritePartIds.has(partId);

    try {
      if (isFav) {
        await api.marketplace.removePartFavourite(partId);
        setFavouritePartIds((prev) => {
          const next = new Set(prev);
          next.delete(partId);
          return next;
        });
      } else {
        await api.marketplace.addPartFavourite(partId);
        setFavouritePartIds((prev) => {
          const next = new Set(prev);
          next.add(partId);
          return next;
        });
      }
    } catch (err: unknown) {
      console.error("Failed to toggle spare part favourite", err);
      const msg = err instanceof Error ? err.message : "Failed to update favourite spare part.";
      setFavouriteError(msg);
    } finally {
      setFavouritePartLoading((prev) => ({ ...prev, [partId]: false }));
    }
  };

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
    setSelectedPartImageIdx(0);
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
          {favouriteError && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-800 flex items-center justify-between">
              <span>{favouriteError}</span>
              <button
                type="button"
                onClick={() => setFavouriteError(null)}
                className="text-rose-500 hover:text-rose-700"
                aria-label="Dismiss favourite error message"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

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
                          src={resolveMediaUrl(v.primary_image_url)}
                          alt={v.title}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
                            const fb = e.currentTarget.parentElement?.querySelector(".vehicle-card-fallback");
                            if (fb) (fb as HTMLElement).style.display = "flex";
                          }}
                        />
                      ) : null}
                      <div
                        className={`vehicle-card-fallback text-center p-4 items-center justify-center flex-col ${
                          v.primary_image_url ? "hidden" : "flex"
                        }`}
                      >
                        <Car className="w-12 h-12 text-slate-700 mx-auto mb-1" />
                        <span className="text-[10px] text-slate-500 font-medium">Verified Dealer Vehicle</span>
                      </div>
                      <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/80 backdrop-blur-md text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Verified Approved</span>
                      </div>
                      {/* Heart Favourite Button */}
                      {user && (
                        <button
                          type="button"
                          onClick={(e) => handleToggleFavourite(e, v.id)}
                          disabled={favouriteLoading[v.id]}
                          aria-label={
                            favouriteVehicleIds.has(v.id)
                              ? `Remove ${v.title} from favourites`
                              : `Save ${v.title} to favourites`
                          }
                          className={`absolute top-3 right-3 p-2 rounded-full backdrop-blur-md transition-all shadow-md focus:outline-none focus:ring-2 focus:ring-amber-400 ${
                            favouriteVehicleIds.has(v.id)
                              ? "bg-rose-500/95 text-white hover:bg-rose-600 border border-rose-400"
                              : "bg-slate-900/80 text-slate-300 hover:text-rose-400 hover:bg-slate-900 border border-slate-700/60"
                          } ${favouriteLoading[v.id] ? "opacity-60 cursor-not-allowed" : ""}`}
                        >
                          {favouriteLoading[v.id] ? (
                            <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          ) : (
                            <Heart
                              className={`w-3.5 h-3.5 transition-transform ${
                                favouriteVehicleIds.has(v.id) ? "fill-current text-white scale-110" : ""
                              }`}
                            />
                          )}
                        </button>
                      )}
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
                        <span className="flex items-center gap-1 truncate">
                          Seller:{" "}
                          <strong className="text-slate-800 truncate">
                            {v.seller_info?.name || v.organisation_name || v.seller_name || "Verified Trader"}
                          </strong>
                          {v.seller_info?.is_verified && (
                            <span title="Verified Seller" className="inline-flex">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                            </span>
                          )}
                        </span>
                        <span className="font-mono text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 flex-shrink-0">
                          VIN: {v.masked_vin || "***********Verified"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="p-5 pt-0 grid grid-cols-2 gap-2">
                    <button
                      onClick={() => {
                        setSelectedVehicle(v);
                        setSelectedVehicleImageIdx(0);
                      }}
                      className="py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>Inspect</span>
                    </button>
                    <button
                      onClick={() => handleOpenEnquiryModal(v)}
                      className="py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-colors flex items-center justify-center gap-1.5 shadow-sm"
                    >
                      <MessageSquare className="w-3.5 h-3.5" />
                      <span>Contact</span>
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
                        <div>
                          {/* Image / Header Banner */}
                          <div className="relative h-44 bg-slate-950 flex items-center justify-center overflow-hidden">
                            {p.primary_image_url ? (
                              <img
                                src={resolveMediaUrl(p.primary_image_url)}
                                alt={p.name}
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
                                  const fb = e.currentTarget.parentElement?.querySelector(".part-card-fallback");
                                  if (fb) (fb as HTMLElement).style.display = "flex";
                                }}
                              />
                            ) : null}
                            <div
                              className={`part-card-fallback text-center p-4 items-center justify-center flex-col ${
                                p.primary_image_url ? "hidden" : "flex"
                              }`}
                            >
                              <Wrench className="w-12 h-12 text-slate-700 mx-auto mb-1" />
                              <span className="text-[10px] text-slate-500 font-medium">Verified Spare Part</span>
                            </div>

                            <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/80 backdrop-blur-md text-[10px] font-bold text-amber-400 border border-amber-500/20">
                              <Tag className="w-3 h-3" />
                              <span>{p.brand}</span>
                            </div>

                            {/* Heart Favourite Button */}
                            {user && (
                              <button
                                type="button"
                                onClick={(e) => handleTogglePartFavourite(e, p.id)}
                                disabled={favouritePartLoading[p.id]}
                                aria-label={
                                  favouritePartIds.has(p.id)
                                    ? `Remove ${p.name} from favourites`
                                    : `Save ${p.name} to favourites`
                                }
                                className={`absolute top-3 right-3 p-2 rounded-full backdrop-blur-md transition-all shadow-md focus:outline-hidden focus:ring-2 focus:ring-amber-400 ${
                                  favouritePartIds.has(p.id)
                                    ? "bg-rose-500/95 text-white hover:bg-rose-600 border border-rose-400"
                                    : "bg-slate-900/80 text-slate-300 hover:text-rose-400 hover:bg-slate-900 border border-slate-700/60"
                                } ${favouritePartLoading[p.id] ? "opacity-60 cursor-not-allowed" : ""}`}
                              >
                                {favouritePartLoading[p.id] ? (
                                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                ) : (
                                  <Heart
                                    className={`w-3.5 h-3.5 transition-transform ${
                                      favouritePartIds.has(p.id) ? "fill-current text-white scale-110" : ""
                                    }`}
                                  />
                                )}
                              </button>
                            )}
                            <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-xl bg-slate-950/90 text-white font-black text-sm text-right leading-tight">
                              <div>₹{p.total_price ? Number(p.total_price).toFixed(2) : (Number(p.price) * (1 + Number(p.gst_rate || 18) / 100)).toFixed(2)}</div>
                              <span className="text-[9px] text-amber-400 font-medium block">incl. GST</span>
                            </div>
                          </div>

                          <div className="p-5 space-y-3">
                            <div className="flex items-center justify-between gap-2">
                              <div>
                                {p.fitment && renderFitmentBadge(p.fitment)}
                              </div>
                              <div>
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

                          <div className="pt-2 border-t border-slate-100 space-y-1">
                            <div className="flex items-baseline justify-between text-xs text-slate-600">
                              <span>Part price:</span>
                              <div className="flex items-baseline gap-1.5">
                                {p.compare_at_price && Number(p.compare_at_price) > Number(p.price) && (
                                  <span className="text-xs text-slate-400 line-through">
                                    ₹{Number(p.compare_at_price).toFixed(2)}
                                  </span>
                                )}
                                <span className="font-semibold text-slate-800">
                                  ₹{Number(p.price).toFixed(2)}
                                </span>
                              </div>
                            </div>
                            <div className="flex items-baseline justify-between text-xs text-slate-600">
                              <span>GST ({p.gst_rate !== undefined && p.gst_rate !== null ? `${Number(p.gst_rate).toFixed(0)}%` : "18%"}):</span>
                              <span className="font-semibold text-slate-800">
                                ₹{p.gst_amount ? Number(p.gst_amount).toFixed(2) : (Number(p.price) * (Number(p.gst_rate || 18) / 100)).toFixed(2)}
                              </span>
                            </div>
                            <div className="flex items-baseline justify-between text-sm font-black text-slate-950 pt-0.5 border-t border-dashed border-slate-200">
                              <span>Total including GST:</span>
                              <span className="text-base text-slate-950 font-black">
                                ₹{p.total_price ? Number(p.total_price).toFixed(2) : (Number(p.price) * (1 + Number(p.gst_rate || 18) / 100)).toFixed(2)}
                              </span>
                            </div>
                            {p.hsn_code && (
                              <div className="text-[10px] text-slate-500 flex items-center justify-between pt-0.5">
                                <span>HSN {p.hsn_code}</span>
                                {p.is_tax_verified ? (
                                  <span className="text-emerald-700 font-medium">✓ Statutory Rate</span>
                                ) : (
                                  <span className="text-amber-700 font-medium">⚠️ Pending Verification</span>
                                )}
                              </div>
                            )}
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
              <div className="flex items-center gap-2">
                {user && (
                  <button
                    type="button"
                    onClick={(e) => handleToggleFavourite(e, selectedVehicle.id)}
                    disabled={favouriteLoading[selectedVehicle.id]}
                    aria-label={
                      favouriteVehicleIds.has(selectedVehicle.id)
                        ? `Remove ${selectedVehicle.title} from favourites`
                        : `Save ${selectedVehicle.title} to favourites`
                    }
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors ${
                      favouriteVehicleIds.has(selectedVehicle.id)
                        ? "bg-rose-50 border-rose-200 text-rose-600 hover:bg-rose-100"
                        : "bg-slate-100 border-slate-200 text-slate-700 hover:bg-slate-200"
                    } ${favouriteLoading[selectedVehicle.id] ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    {favouriteLoading[selectedVehicle.id] ? (
                      <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <Heart
                        className={`w-3.5 h-3.5 ${
                          favouriteVehicleIds.has(selectedVehicle.id) ? "fill-current text-rose-600" : ""
                        }`}
                      />
                    )}
                    <span>
                      {favouriteVehicleIds.has(selectedVehicle.id) ? "Saved in Favourites" : "Save to Favourites"}
                    </span>
                  </button>
                )}
                <button
                  onClick={() => setSelectedVehicle(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {(() => {
              const gallery = [selectedVehicle.primary_image_url, ...(selectedVehicle.images || [])]
                .filter((url, idx, arr): url is string => Boolean(url && url.trim()) && arr.indexOf(url) === idx);
              const activeIdx = Math.min(selectedVehicleImageIdx, Math.max(0, gallery.length - 1));
              const activeImage = gallery[activeIdx];

              if (gallery.length === 0) {
                return (
                  <div className="rounded-2xl h-52 bg-slate-950 flex flex-col items-center justify-center text-slate-500">
                    <Car className="w-12 h-12 text-slate-700 mb-2" />
                    <span className="text-xs">No photos provided for this vehicle</span>
                  </div>
                );
              }

              return (
                <div className="space-y-3">
                  <div className="relative rounded-2xl overflow-hidden h-72 bg-slate-950 flex items-center justify-center">
                    <img
                      src={resolveMediaUrl(activeImage)}
                      alt={`${selectedVehicle.title} - photo ${activeIdx + 1}`}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        const fb = e.currentTarget.parentElement?.querySelector(".gallery-vehicle-fallback");
                        if (fb) (fb as HTMLElement).style.display = "flex";
                      }}
                    />
                    <div className="gallery-vehicle-fallback hidden flex-col items-center justify-center text-slate-500 p-6 text-center">
                      <ImageIcon className="w-12 h-12 text-slate-700 mb-2" />
                      <span className="text-xs font-semibold text-slate-400">Photo could not be loaded</span>
                      <span className="text-[10px] text-slate-600 mt-1 max-w-xs break-all">{activeImage}</span>
                    </div>

                    {gallery.length > 1 && (
                      <>
                        <button
                          type="button"
                          onClick={() => setSelectedVehicleImageIdx((prev) => (prev > 0 ? prev - 1 : gallery.length - 1))}
                          className="absolute left-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-slate-900/80 hover:bg-slate-900 text-white backdrop-blur-md transition-all shadow-md"
                          aria-label="Previous photo"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedVehicleImageIdx((prev) => (prev < gallery.length - 1 ? prev + 1 : 0))}
                          className="absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-slate-900/80 hover:bg-slate-900 text-white backdrop-blur-md transition-all shadow-md"
                          aria-label="Next photo"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                        <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-lg bg-slate-950/80 backdrop-blur-md text-white text-[10px] font-bold">
                          {activeIdx + 1} / {gallery.length} Photos
                        </div>
                      </>
                    )}
                  </div>

                  {gallery.length > 1 && (
                    <div className="flex items-center gap-2 overflow-x-auto pb-1">
                      {gallery.map((url, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setSelectedVehicleImageIdx(idx)}
                          className={`relative flex-shrink-0 w-16 h-16 rounded-xl overflow-hidden border-2 transition-all ${
                            idx === activeIdx
                              ? "border-amber-400 ring-2 ring-amber-400/40"
                              : "border-slate-200 hover:border-slate-400 opacity-70 hover:opacity-100"
                          }`}
                        >
                          <img
                            src={resolveMediaUrl(url)}
                            alt={`Thumbnail ${idx + 1}`}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                            }}
                          />
                          {idx === 0 && (
                            <span className="absolute bottom-0 inset-x-0 bg-slate-900/80 text-[8px] font-bold text-amber-400 text-center py-0.5">
                              Main
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })()}

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

            {/* Seller Information & Authorized Direct Contact */}
            <div className="p-4 bg-slate-900 text-white rounded-2xl space-y-3 shadow-md border border-slate-800">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-amber-400" />
                  <h5 className="font-bold text-sm text-white">Seller Information</h5>
                </div>
                {selectedVehicle.seller_info?.is_verified ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    Verified Seller
                  </span>
                ) : (
                  <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded-full border border-slate-700">
                    Standard Seller
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-[10px] text-slate-400 block">Seller / Dealership Name</span>
                  <span className="font-bold text-slate-100 text-sm">
                    {selectedVehicle.seller_info?.name || selectedVehicle.organisation_name || selectedVehicle.seller_name || "Private Seller"}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 block">Seller Classification</span>
                  <span className="font-medium text-slate-200">
                    {selectedVehicle.seller_info?.seller_type === "DEALERSHIP" ? "Automotive Dealership" : "Individual Seller"}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 block">Location</span>
                  <span className="font-medium text-slate-200 flex items-center gap-1">
                    <MapPin className="w-3 h-3 text-slate-400" />
                    {selectedVehicle.seller_info?.location_city || selectedVehicle.location_city || "Location available upon enquiry"}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 block">Public Business Phone</span>
                  <span className="font-mono text-slate-200">
                    {selectedVehicle.seller_info?.phone || "Direct phone not listed (Use enquiry)"}
                  </span>
                </div>
              </div>

              {/* Direct Communication Buttons */}
              <div className="pt-2 border-t border-slate-800 flex flex-wrap gap-2">
                {selectedVehicle.seller_info?.phone && (
                  <a
                    href={`tel:${selectedVehicle.seller_info.phone}`}
                    className="flex-1 min-w-[130px] py-2 px-3 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors border border-slate-700"
                  >
                    <Phone className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Call Seller</span>
                  </a>
                )}

                {selectedVehicle.seller_info?.whatsapp_url && (
                  <a
                    href={selectedVehicle.seller_info.whatsapp_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 min-w-[130px] py-2 px-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                  >
                    <MessageCircle className="w-3.5 h-3.5" />
                    <span>WhatsApp</span>
                  </a>
                )}

                <button
                  type="button"
                  onClick={() => {
                    const target = selectedVehicle;
                    setSelectedVehicle(null);
                    handleOpenEnquiryModal(target);
                  }}
                  className="flex-1 min-w-[150px] py-2 px-3 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-xl text-xs font-black flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                >
                  <MessageSquare className="w-3.5 h-3.5 text-slate-950" />
                  <span>Contact Seller</span>
                </button>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-between border-t border-slate-100">
              <button
                type="button"
                onClick={() => {
                  const target = selectedVehicle;
                  setSelectedVehicle(null);
                  handleOpenEnquiryModal(target);
                }}
                className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all flex items-center gap-1.5 shadow-sm"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Contact Seller Directly</span>
              </button>
              <button
                onClick={() => setSelectedVehicle(null)}
                className="px-5 py-2.5 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800"
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
              <div className="flex items-center gap-2">
                {user && (
                  <button
                    type="button"
                    onClick={(e) => handleTogglePartFavourite(e, selectedPart.id)}
                    disabled={favouritePartLoading[selectedPart.id]}
                    aria-label={
                      favouritePartIds.has(selectedPart.id)
                        ? `Remove ${selectedPart.name} from favourites`
                        : `Save ${selectedPart.name} to favourites`
                    }
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors ${
                      favouritePartIds.has(selectedPart.id)
                        ? "bg-rose-50 border-rose-200 text-rose-600 hover:bg-rose-100"
                        : "bg-slate-100 border-slate-200 text-slate-700 hover:bg-slate-200"
                    } ${favouritePartLoading[selectedPart.id] ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    {favouritePartLoading[selectedPart.id] ? (
                      <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <Heart
                        className={`w-3.5 h-3.5 ${
                          favouritePartIds.has(selectedPart.id) ? "fill-current text-rose-600" : ""
                        }`}
                      />
                    )}
                    <span>
                      {favouritePartIds.has(selectedPart.id) ? "Saved in Favourites" : "Save to Favourites"}
                    </span>
                  </button>
                )}
                <button
                  onClick={() => setSelectedPart(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Multi-image gallery for spare part */}
            {(() => {
              const gallery = [selectedPart.primary_image_url, ...(selectedPart.images || [])]
                .filter((url, idx, arr): url is string => Boolean(url && url.trim()) && arr.indexOf(url) === idx);
              const activeIdx = Math.min(selectedPartImageIdx, Math.max(0, gallery.length - 1));
              const activeImage = gallery[activeIdx];

              if (gallery.length === 0) {
                return (
                  <div className="rounded-2xl h-48 bg-slate-950 flex flex-col items-center justify-center text-slate-500">
                    <Wrench className="w-12 h-12 text-slate-700 mb-2" />
                    <span className="text-xs">No photos provided for this spare part</span>
                  </div>
                );
              }

              return (
                <div className="space-y-3">
                  <div className="relative rounded-2xl overflow-hidden h-64 bg-slate-950 flex items-center justify-center">
                    <img
                      src={resolveMediaUrl(activeImage)}
                      alt={`${selectedPart.name} - photo ${activeIdx + 1}`}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        const fb = e.currentTarget.parentElement?.querySelector(".gallery-part-fallback");
                        if (fb) (fb as HTMLElement).style.display = "flex";
                      }}
                    />
                    <div className="gallery-part-fallback hidden flex-col items-center justify-center text-slate-500 p-6 text-center">
                      <ImageIcon className="w-12 h-12 text-slate-700 mb-2" />
                      <span className="text-xs font-semibold text-slate-400">Photo could not be loaded</span>
                      <span className="text-[10px] text-slate-600 mt-1 max-w-xs break-all">{activeImage}</span>
                    </div>

                    {gallery.length > 1 && (
                      <>
                        <button
                          type="button"
                          onClick={() => setSelectedPartImageIdx((prev) => (prev > 0 ? prev - 1 : gallery.length - 1))}
                          className="absolute left-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-slate-900/80 hover:bg-slate-900 text-white backdrop-blur-md transition-all shadow-md"
                          aria-label="Previous photo"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedPartImageIdx((prev) => (prev < gallery.length - 1 ? prev + 1 : 0))}
                          className="absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-slate-900/80 hover:bg-slate-900 text-white backdrop-blur-md transition-all shadow-md"
                          aria-label="Next photo"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                        <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-lg bg-slate-950/80 backdrop-blur-md text-white text-[10px] font-bold">
                          {activeIdx + 1} / {gallery.length} Photos
                        </div>
                      </>
                    )}
                  </div>

                  {gallery.length > 1 && (
                    <div className="flex items-center gap-2 overflow-x-auto pb-1">
                      {gallery.map((url, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setSelectedPartImageIdx(idx)}
                          className={`relative flex-shrink-0 w-16 h-16 rounded-xl overflow-hidden border-2 transition-all ${
                            idx === activeIdx
                              ? "border-amber-400 ring-2 ring-amber-400/40"
                              : "border-slate-200 hover:border-slate-400 opacity-70 hover:opacity-100"
                          }`}
                        >
                          <img
                            src={resolveMediaUrl(url)}
                            alt={`Thumbnail ${idx + 1}`}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                            }}
                          />
                          {idx === 0 && (
                            <span className="absolute bottom-0 inset-x-0 bg-slate-900/80 text-[8px] font-bold text-amber-400 text-center py-0.5">
                              Main
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })()}

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Part Price (excl. GST)</span>
                <div className="flex items-baseline gap-1.5 mt-0.5">
                  {selectedPart.compare_at_price && Number(selectedPart.compare_at_price) > Number(selectedPart.price) && (
                    <span className="text-xs text-slate-400 line-through">
                      ₹{Number(selectedPart.compare_at_price).toFixed(2)}
                    </span>
                  )}
                  <p className="font-black text-base text-slate-950">
                    ₹{Number(selectedPart.price).toFixed(2)}
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

            {/* Statutory Indian GST Breakdown Panel */}
            <div className="p-4 bg-gradient-to-br from-slate-900 to-slate-950 text-white rounded-2xl border border-slate-800 space-y-3 shadow-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 text-[10px] font-bold border border-amber-500/30">
                    GST Tax Breakdown (Indian CBIC Standard)
                  </span>
                  {selectedPart.hsn_code && (
                    <span className="text-[11px] text-slate-300 font-mono">
                      HSN: <strong className="text-white">{selectedPart.hsn_code}</strong>
                    </span>
                  )}
                </div>
                {selectedPart.is_tax_verified ? (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-500/30">
                    <CheckCircle2 className="w-3 h-3" />
                    Statutory Rate Verified
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded-full border border-amber-500/30">
                    <AlertTriangle className="w-3 h-3" />
                    Pending Tax Verification
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/50">
                  <span className="text-[10px] text-slate-400 block">Part Price (before GST)</span>
                  <span className="text-base font-bold text-slate-100 font-mono">
                    ₹{Number(selectedPart.price).toFixed(2)}
                  </span>
                </div>
                <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/50">
                  <span className="text-[10px] text-slate-400 block">
                    Applicable GST ({selectedPart.gst_rate !== undefined && selectedPart.gst_rate !== null ? `${Number(selectedPart.gst_rate).toFixed(0)}%` : "18%"})
                  </span>
                  <span className="text-base font-bold text-amber-400 font-mono">
                    ₹{selectedPart.gst_amount ? Number(selectedPart.gst_amount).toFixed(2) : (Number(selectedPart.price) * (Number(selectedPart.gst_rate || 18) / 100)).toFixed(2)}
                  </span>
                </div>
                <div className="p-3 bg-amber-500/10 rounded-xl border border-amber-500/30">
                  <span className="text-[10px] text-amber-300 block font-medium">Total (inclusive of GST)</span>
                  <span className="text-lg font-black text-amber-400 font-mono">
                    ₹{selectedPart.total_price ? Number(selectedPart.total_price).toFixed(2) : (Number(selectedPart.price) * (1 + Number(selectedPart.gst_rate || 18) / 100)).toFixed(2)}
                  </span>
                </div>
              </div>

              {selectedPart.tax_breakdown && (
                <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between text-[11px] text-slate-400">
                  <div className="flex items-center gap-3">
                    <span>CGST: <strong className="text-slate-200">₹{Number(selectedPart.tax_breakdown.cgst_amount || 0).toFixed(2)}</strong></span>
                    <span>SGST: <strong className="text-slate-200">₹{Number(selectedPart.tax_breakdown.sgst_amount || 0).toFixed(2)}</strong></span>
                    <span>IGST: <strong className="text-slate-200">₹{Number(selectedPart.tax_breakdown.igst_amount || 0).toFixed(2)}</strong></span>
                  </div>
                  <span className="text-[10px] text-slate-500 italic">
                    {selectedPart.tax_breakdown.is_interstate ? "Inter-state supply (IGST)" : "Intra-state supply (CGST + SGST)"}
                  </span>
                </div>
              )}
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
                            <div className="flex flex-col items-end">
                              <div className="flex items-baseline gap-1.5">
                                {offer.compare_at_price && Number(offer.compare_at_price) > Number(offer.price) && (
                                  <span className="text-xs text-slate-400 line-through font-mono">
                                    ₹{Number(offer.compare_at_price).toFixed(2)}
                                  </span>
                                )}
                                <span className="text-sm font-black text-slate-950 font-mono">
                                  ₹{Number(offer.price).toFixed(2)}
                                </span>
                              </div>
                              {offer.gst_rate !== undefined && (
                                <span className="text-[10px] text-slate-500 font-mono">
                                  + {Number(offer.gst_rate).toFixed(0)}% GST = ₹{Number(offer.total_price || (Number(offer.price) * (1 + Number(offer.gst_rate)/100))).toFixed(2)}
                                </span>
                              )}
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

      {/* =========================================================================
          MODAL: DIRECT BUYER-SELLER VEHICLE ENQUIRY
      ========================================================================= */}
      {enquiryVehicle && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
                  <MessageSquare className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-black text-slate-900">Contact Seller</h3>
                  <p className="text-xs text-slate-500">Direct Vehicle Purchase Enquiry</p>
                </div>
              </div>
              <button
                onClick={() => setEnquiryVehicle(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Vehicle Summary Card */}
            <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 flex items-center gap-3">
              {enquiryVehicle.primary_image_url ? (
                <img
                  src={resolveMediaUrl(enquiryVehicle.primary_image_url)}
                  alt={enquiryVehicle.title}
                  className="w-14 h-14 rounded-xl object-cover border border-slate-200 flex-shrink-0"
                />
              ) : (
                <div className="w-14 h-14 rounded-xl bg-slate-200 flex items-center justify-center text-slate-400 flex-shrink-0">
                  <Car className="w-6 h-6" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <h4 className="text-xs font-black text-slate-900 truncate">{enquiryVehicle.title}</h4>
                <div className="text-[11px] text-slate-500">
                  <span>£{Number(enquiryVehicle.price).toLocaleString()}</span>
                  <span className="mx-1.5">·</span>
                  <span>{enquiryVehicle.year}</span>
                  <span className="mx-1.5">·</span>
                  <span>{enquiryVehicle.location_city || "UK"}</span>
                </div>
                <div className="text-[10px] text-slate-600 mt-0.5 flex items-center gap-1">
                  <span>
                    Seller: <strong>{enquiryVehicle.seller_info?.name || enquiryVehicle.seller_name || "Verified Trader"}</strong>
                  </span>
                  {enquiryVehicle.seller_info?.is_verified && (
                    <CheckCircle2 className="w-3 h-3 text-emerald-500 inline" />
                  )}
                </div>
              </div>
            </div>

            {/* Success State */}
            {enquirySuccess ? (
              <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-emerald-900 text-xs space-y-2">
                <div className="flex items-center gap-2 font-bold text-emerald-800">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Enquiry Sent Successfully</span>
                </div>
                <p className="text-emerald-700 leading-relaxed">{enquirySuccess}</p>
                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() => setEnquiryVehicle(null)}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl text-xs"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSendEnquiry} className="space-y-4">
                {enquiryError && (
                  <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
                    <span>{enquiryError}</span>
                  </div>
                )}

                {!user && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-xs flex items-center gap-2">
                    <Info className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <span>You must be signed in to submit an enquiry to vehicle sellers.</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Your Enquiry Message <span className="text-rose-500">*</span>
                  </label>
                  <textarea
                    rows={4}
                    value={enquiryMessage}
                    onChange={(e) => setEnquiryMessage(e.target.value)}
                    placeholder="Describe your questions about condition, availability, or pricing..."
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:bg-white resize-none"
                    required
                  />
                  <span className="text-[10px] text-slate-400 block mt-1">
                    Prefilled with recommended buyer questions. Feel free to customize before sending.
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Your Contact Phone Number <span className="text-slate-400 font-normal">(Optional Callback)</span>
                  </label>
                  <input
                    type="tel"
                    value={enquiryBuyerPhone}
                    onChange={(e) => setEnquiryBuyerPhone(e.target.value)}
                    placeholder="+44 7123 456789"
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:bg-white"
                  />
                  <span className="text-[10px] text-slate-400 block mt-1">
                    Sellers can use this to call or text you regarding this vehicle.
                  </span>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-[11px] text-slate-600 flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                  <span>
                    Your identity is verified via your DriverXtra account. Sensitive credentials are never exposed.
                  </span>
                </div>

                <div className="pt-2 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setEnquiryVehicle(null)}
                    className="px-4 py-2.5 text-xs font-bold text-slate-600 hover:text-slate-900 rounded-xl"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={enquirySubmitting || !user}
                    className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {enquirySubmitting ? (
                      <>
                        <div className="w-3.5 h-3.5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                        <span>Sending...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-3.5 h-3.5" />
                        <span>Send Enquiry</span>
                      </>
                    )}
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
