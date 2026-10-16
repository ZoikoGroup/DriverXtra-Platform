"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  PartSummary,
  PartDetail,
  PartCategory,
  VehicleMake,
  VehicleModel,
  VehicleVariant,
  GarageVehicle,
  FitmentEvaluation,
  ApiError
} from "@/lib/api/client";
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Car,
  Layers,
  Wrench,
  ChevronRight,
  RefreshCw,
  X,
  FileCheck2
} from "lucide-react";

export default function Phase2CatalogueView() {
  // Catalogue state
  const [parts, setParts] = useState<PartSummary[]>([]);
  const [categories, setCategories] = useState<PartCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedBrand, setSelectedBrand] = useState<string>("");
  const [isLoadingParts, setIsLoadingParts] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Selected Part Detail
  const [selectedPart, setSelectedPart] = useState<PartDetail | null>(null);
  const [isLoadingPartDetail, setIsLoadingPartDetail] = useState<boolean>(false);

  // Vehicle Hierarchy Filter
  const [makes, setMakes] = useState<VehicleMake[]>([]);
  const [models, setModels] = useState<VehicleModel[]>([]);
  const [variants, setVariants] = useState<VehicleVariant[]>([]);
  const [filterMakeId, setFilterMakeId] = useState("");
  const [filterModelId, setFilterModelId] = useState("");
  const [filterVariantId, setFilterVariantId] = useState("");

  // User Garage vehicles for quick fitment evaluation
  const [garageVehicles, setGarageVehicles] = useState<GarageVehicle[]>([]);
  const [selectedGarageVehicleId, setSelectedGarageVehicleId] = useState<string>("");

  // Fitment Evaluation Results
  const [evaluatingFitment, setEvaluatingFitment] = useState(false);
  const [fitmentResult, setFitmentResult] = useState<{
    partId: string;
    variantId: string;
    evaluation: FitmentEvaluation;
  } | null>(null);

  // Load initial data
  useEffect(() => {
    let ignore = false;
    // 1. Categories
    api.catalogue.getCategories().then((res) => {
      if (!ignore) setCategories(res);
    }).catch(() => {});
    // 2. Makes
    api.catalogue.getMakes().then((res) => {
      if (!ignore) setMakes(res);
    }).catch(() => {});
    // 3. User's Garage vehicles (if authenticated)
    api.garage.listVehicles().then((vehs) => {
      if (!ignore) {
        setGarageVehicles(vehs);
        const primary = vehs.find((v) => v.is_primary) || vehs[0];
        if (primary) {
          setSelectedGarageVehicleId(primary.id);
          if (primary.vehicle_variant) {
            setFilterVariantId(primary.vehicle_variant);
          }
        }
      }
    }).catch(() => {});

    return () => {
      ignore = true;
    };
  }, []);

  // Cascading Models
  useEffect(() => {
    if (!filterMakeId) return;
    let ignore = false;
    api.catalogue.getModels(filterMakeId).then((res) => {
      if (!ignore) setModels(res);
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, [filterMakeId]);

  // Cascading Variants
  useEffect(() => {
    if (!filterModelId) return;
    let ignore = false;
    api.catalogue.getVariants(filterModelId).then((res) => {
      if (!ignore) setVariants(res);
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, [filterModelId]);

  // Load Parts
  const loadParts = useCallback(async () => {
    try {
      setIsLoadingParts(true);
      setErrorMsg(null);
      const data = await api.catalogue.getParts({
        category: selectedCategory || undefined,
        brand: selectedBrand || undefined,
        search: searchQuery.trim() || undefined,
      });
      setParts(data);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to load parts catalogue.");
    } finally {
      setIsLoadingParts(false);
    }
  }, [selectedCategory, selectedBrand, searchQuery]);

  useEffect(() => {
    let ignore = false;
    api.catalogue.getParts({
      category: selectedCategory || undefined,
      brand: selectedBrand || undefined,
      search: searchQuery.trim() || undefined,
    }).then((data) => {
      if (!ignore) {
        setParts(data);
        setIsLoadingParts(false);
      }
    }).catch((err: unknown) => {
      if (!ignore) {
        setErrorMsg(err instanceof ApiError ? err.message : "Failed to load parts catalogue.");
        setIsLoadingParts(false);
      }
    });

    return () => {
      ignore = true;
    };
  }, [selectedCategory, selectedBrand, searchQuery]);

  // View part detail
  const handleSelectPart = async (partId: string) => {
    try {
      setIsLoadingPartDetail(true);
      setErrorMsg(null);
      const detail = await api.catalogue.getPart(partId);
      setSelectedPart(detail);
      setFitmentResult(null); // Reset previous evaluation
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to load part details.");
    } finally {
      setIsLoadingPartDetail(false);
    }
  };

  // Run Fitment Check for Selected Part
  const handleCheckFitment = async (partId: string, variantId: string) => {
    if (!variantId) {
      setErrorMsg("Please select a target vehicle variant or garage vehicle to check fitment.");
      return;
    }
    try {
      setEvaluatingFitment(true);
      setErrorMsg(null);
      const result = await api.catalogue.evaluateFitment(partId, variantId);
      setFitmentResult({
        partId,
        variantId,
        evaluation: result,
      });
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Fitment evaluation failed.");
    } finally {
      setEvaluatingFitment(false);
    }
  };

  // Determine current active variant ID (either from garage selection or cascade)
  const effectiveVariantId = selectedGarageVehicleId
    ? garageVehicles.find((v) => v.id === selectedGarageVehicleId)?.vehicle_variant || filterVariantId
    : filterVariantId;

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-amber-400 text-slate-950 font-black text-xs">
              Phase 2
            </span>
            <h1 className="text-xl font-black text-slate-950">Vehicle & Spare-Parts Catalogue</h1>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Browse canonical automotive parts, OEM cross-references, and test vehicle compatibility against real engineering data.
          </p>
        </div>

        <button
          onClick={loadParts}
          disabled={isLoadingParts}
          className="p-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 transition-colors self-start sm:self-auto"
          title="Refresh Catalogue"
        >
          <RefreshCw className={`w-4 h-4 ${isLoadingParts ? "animate-spin text-amber-500" : ""}`} />
        </button>
      </div>

      {/* Confirmed Fitment Selector Banner */}
      <div className="bg-slate-950 text-white rounded-2xl p-5 border border-slate-800 shadow-md flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-400 text-slate-950 flex items-center justify-center font-black shrink-0">
            <Car className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-amber-400">
              Confirmed Fitment Context
            </span>
            <h4 className="text-sm font-black text-white">
              Evaluate Compatibility for Your Vehicle
            </h4>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {garageVehicles.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-400">My Garage:</span>
              <select
                value={selectedGarageVehicleId}
                onChange={(e) => {
                  setSelectedGarageVehicleId(e.target.value);
                  const found = garageVehicles.find((v) => v.id === e.target.value);
                  if (found?.vehicle_variant) {
                    setFilterVariantId(found.vehicle_variant);
                  }
                }}
                className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white font-medium focus:outline-none focus:ring-1 focus:ring-amber-400"
              >
                <option value="">-- Manual Catalogue Hierarchy --</option>
                {garageVehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.year} {v.make} {v.model} {v.registration_plate ? `[${v.registration_plate}]` : ""} {v.is_primary ? "★" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Quick Make/Model selector fallback if not using garage */}
          {!selectedGarageVehicleId && (
            <div className="flex items-center gap-2">
              <select
                value={filterMakeId}
                onChange={(e) => {
                  setFilterMakeId(e.target.value);
                  setFilterModelId("");
                  setFilterVariantId("");
                  setModels([]);
                  setVariants([]);
                }}
                className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white font-medium focus:outline-none focus:ring-1 focus:ring-amber-400"
              >
                <option value="">Make</option>
                {makes.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>

              <select
                value={filterModelId}
                onChange={(e) => {
                  setFilterModelId(e.target.value);
                  setFilterVariantId("");
                  setVariants([]);
                }}
                disabled={!filterMakeId}
                className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white font-medium focus:outline-none focus:ring-1 focus:ring-amber-400 disabled:opacity-40"
              >
                <option value="">Model</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>

              <select
                value={filterVariantId}
                onChange={(e) => setFilterVariantId(e.target.value)}
                disabled={!filterModelId}
                className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white font-medium focus:outline-none focus:ring-1 focus:ring-amber-400 disabled:opacity-40"
              >
                <option value="">Variant / Trim</option>
                {variants.map((v) => (
                  <option key={v.id} value={v.id}>{v.year} {v.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2">
            <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search parts by name, manufacturer part number, or keyword..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
          />
        </div>

        {/* Category Filter */}
        <div className="flex items-center gap-3">
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white font-medium focus:outline-none focus:ring-2 focus:ring-amber-400"
          >
            <option value="">All Categories</option>
            {categories.map((cat) => (
              <React.Fragment key={cat.id}>
                <option value={cat.id} className="font-bold">
                  {cat.name}
                </option>
                {cat.subcategories?.map((sub) => (
                  <option key={sub.id} value={sub.id}>
                    &nbsp;&nbsp;↳ {sub.name}
                  </option>
                ))}
              </React.Fragment>
            ))}
          </select>

          <input
            type="text"
            placeholder="Filter Brand (e.g. Bosch)"
            value={selectedBrand}
            onChange={(e) => setSelectedBrand(e.target.value)}
            className="px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 w-36"
          />
        </div>
      </div>

      {/* Main Grid: Parts List + Inspector Modal/Column */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Parts Cards (Left 2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between text-xs font-bold text-slate-600 px-1">
            <span>{parts.length} Canonical Parts Found</span>
            <span className="text-[11px] font-normal text-slate-500">Live DRF data via <code className="font-mono">/api/v1/catalogue/parts/</code></span>
          </div>

          {isLoadingParts ? (
            <div className="p-16 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
              <div className="w-8 h-8 border-3 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <p className="text-xs font-bold text-slate-700">Loading parts catalogue...</p>
            </div>
          ) : parts.length === 0 ? (
            <div className="p-16 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
              <Layers className="w-8 h-8 text-slate-300 mx-auto" />
              <h4 className="text-sm font-bold text-slate-800">No catalogue parts match your query</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Try adjusting your search query, brand filter, or selecting a different category.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {parts.map((part) => {
                const isSelected = selectedPart?.id === part.id;
                return (
                  <div
                    key={part.id}
                    onClick={() => handleSelectPart(part.id)}
                    className={`cursor-pointer bg-white rounded-2xl p-5 border transition-all flex flex-col justify-between ${
                      isSelected
                        ? "border-amber-400 ring-2 ring-amber-400/20 shadow-md"
                        : "border-slate-200 hover:border-slate-300 shadow-sm"
                    }`}
                  >
                    <div>
                      {/* Top Badges */}
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                          {part.category_name || "Automotive"}
                        </span>
                        {part.is_universal && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300">
                            Universal Fit
                          </span>
                        )}
                      </div>

                      {/* Part Name & Brand */}
                      <div className="text-[11px] uppercase font-bold text-amber-600 tracking-wider">
                        {part.brand}
                      </div>
                      <h3 className="text-sm font-black text-slate-950 mt-0.5 line-clamp-2">
                        {part.name}
                      </h3>

                      {/* Part Number & OEM */}
                      <div className="mt-3 pt-3 border-t border-slate-100 space-y-1.5 text-xs">
                        <div className="flex justify-between">
                          <span className="text-slate-500 text-[11px]">MPN:</span>
                          <span className="font-mono font-bold text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded text-[11px]">
                            {part.part_number}
                          </span>
                        </div>

                        {part.oem_numbers && part.oem_numbers.length > 0 && (
                          <div className="flex justify-between text-[11px]">
                            <span className="text-slate-500">OEM Cross:</span>
                            <span className="font-mono text-slate-700 font-semibold truncate max-w-[140px]">
                              {part.oem_numbers.join(", ")}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Bottom Actions & Compatibility Tag */}
                    <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                      <span className="text-[11px] text-slate-500 font-medium">
                        {part.compatibilities_count ?? 0} mapped variants
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectPart(part.id);
                        }}
                        className="text-amber-600 hover:text-amber-700 font-bold text-xs flex items-center gap-1"
                      >
                        <span>Details & Fitment</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Part Detail & Confirmed Fitment Inspector (Right col) */}
        <div className="space-y-4">
          {isLoadingPartDetail ? (
            <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
              <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <p className="text-xs font-bold text-slate-700">Loading part details & compatibilities...</p>
            </div>
          ) : selectedPart ? (
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-5 sticky top-6">
              {/* Header */}
              <div className="pb-3 border-b border-slate-100">
                <div className="text-[10px] font-black uppercase tracking-wider text-amber-500">
                  {selectedPart.brand} • {selectedPart.category_name}
                </div>
                <h3 className="text-base font-black text-slate-950 mt-1">
                  {selectedPart.name}
                </h3>
                <div className="mt-2 flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">
                    MPN: {selectedPart.part_number}
                  </span>
                  {selectedPart.is_universal && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800">
                      Universal
                    </span>
                  )}
                </div>
              </div>

              {/* Technical Specifications */}
              {selectedPart.technical_specs && Object.keys(selectedPart.technical_specs).length > 0 && (
                <div className="space-y-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Technical Specifications
                  </span>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(selectedPart.technical_specs).map(([key, val]) => (
                      <div key={key} className="p-2 bg-slate-50 rounded-xl border border-slate-100">
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">{key}</div>
                        <div className="font-bold text-slate-800 truncate">{String(val)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* OEM Reference Numbers */}
              {selectedPart.oem_numbers && selectedPart.oem_numbers.length > 0 && (
                <div className="space-y-1.5">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    OEM Reference Numbers
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedPart.oem_numbers.map((oem) => (
                      <span
                        key={oem}
                        className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded-md text-[11px] font-mono font-bold"
                      >
                        {oem}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Fitment Evaluation Box */}
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-black uppercase tracking-wider text-slate-900 flex items-center gap-1.5">
                    <Wrench className="w-3.5 h-3.5 text-amber-500" />
                    Confirmed Fitment Check
                  </span>
                </div>

                <div className="text-xs text-slate-600">
                  {effectiveVariantId ? (
                    <span>Ready to check fitment against active vehicle.</span>
                  ) : (
                    <span className="text-amber-700">Select a vehicle from your garage or the dropdown above to run fitment check.</span>
                  )}
                </div>

                <button
                  onClick={() => handleCheckFitment(selectedPart.id, effectiveVariantId)}
                  disabled={!effectiveVariantId || evaluatingFitment}
                  className="w-full bg-slate-950 hover:bg-slate-800 text-white font-bold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
                >
                  {evaluatingFitment ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />
                      <span>Evaluating Fitment...</span>
                    </>
                  ) : (
                    <>
                      <FileCheck2 className="w-3.5 h-3.5 text-amber-400" />
                      <span>Check Fitment Compatibility</span>
                    </>
                  )}
                </button>

                {/* Fitment Evaluation Result Badge & Details */}
                {fitmentResult && fitmentResult.partId === selectedPart.id && (
                  <div className="mt-3 pt-3 border-t border-slate-200 space-y-2">
                    {fitmentResult.evaluation.outcome === "CONFIRMED_FIT" && (
                      <div className="p-3 bg-emerald-50 border border-emerald-300 rounded-xl text-emerald-900 text-xs space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 font-black">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                            <span>CONFIRMED FIT</span>
                          </div>
                          {fitmentResult.evaluation.evidence_level && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-200/60 text-emerald-950">
                              Evidence: {fitmentResult.evaluation.evidence_level.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] font-medium text-emerald-800">
                          {fitmentResult.evaluation.reason || "This part has verified engineering compatibility with your selected vehicle."}
                        </p>
                        {fitmentResult.evaluation.position && (
                          <div className="text-[10px] font-semibold text-emerald-700">
                            Fitment Position: {fitmentResult.evaluation.position}
                          </div>
                        )}
                      </div>
                    )}

                    {fitmentResult.evaluation.outcome === "CONDITIONAL_FIT" && (
                      <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 text-xs space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 font-black">
                            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                            <span>CONDITIONAL FIT</span>
                          </div>
                          {fitmentResult.evaluation.evidence_level && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-200/70 text-amber-950">
                              Evidence: {fitmentResult.evaluation.evidence_level.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] font-medium text-amber-800">
                          {fitmentResult.evaluation.reason || fitmentResult.evaluation.notes || "Fitment requires verification against chassis or year bounds."}
                        </p>
                      </div>
                    )}

                    {fitmentResult.evaluation.outcome === "DOES_NOT_FIT" && (
                      <div className="p-3 bg-rose-50 border border-rose-300 rounded-xl text-rose-900 text-xs space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 font-black">
                            <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
                            <span>DOES NOT FIT</span>
                          </div>
                          {fitmentResult.evaluation.evidence_level && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-rose-200/60 text-rose-950">
                              Evidence: {fitmentResult.evaluation.evidence_level.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] font-medium text-rose-800">
                          {fitmentResult.evaluation.reason || "Explicit engineering exclusion: this component is incompatible with this vehicle variant."}
                        </p>
                      </div>
                    )}

                    {fitmentResult.evaluation.outcome === "UNKNOWN" && (
                      <div className="p-3 bg-slate-100 border border-slate-300 rounded-xl text-slate-800 text-xs space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 font-black">
                            <HelpCircle className="w-4 h-4 text-slate-500 shrink-0" />
                            <span>UNKNOWN COMPATIBILITY</span>
                          </div>
                          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                            No Verified Record
                          </span>
                        </div>
                        <p className="text-[11px] font-medium text-slate-600">
                          {fitmentResult.evaluation.reason || "No verified compatibility record exists for this part and vehicle combination. Do not assume compatibility."}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Direct Fit Mappings List */}
              <div className="space-y-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Known Compatible Vehicles ({selectedPart.compatibilities?.length ?? 0})
                </span>

                {selectedPart.compatibilities && selectedPart.compatibilities.length > 0 ? (
                  <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                    {selectedPart.compatibilities.map((c) => (
                      <div
                        key={c.id}
                        className="p-2.5 bg-slate-50 rounded-xl border border-slate-200 text-xs flex items-center justify-between"
                      >
                        <div>
                          <div className="font-bold text-slate-900">
                            {c.vehicle_display || "Vehicle Variant"}
                          </div>
                          {c.fitment_notes && (
                            <div className="text-[10px] text-slate-500 italic">
                              {c.fitment_notes}
                            </div>
                          )}
                        </div>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                          Direct Fit
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">
                    {selectedPart.is_universal ? "Universal part — compatible with standard vehicle applications." : "No explicit compatibility records mapped."}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-xs text-slate-500">
              Select a part from the catalogue to inspect specifications, OEM cross-references, and run confirmed fitment evaluation.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
