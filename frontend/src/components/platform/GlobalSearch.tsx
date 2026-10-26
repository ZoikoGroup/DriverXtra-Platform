"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  api,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  PartSummary,
  GarageVehicle,
} from "@/lib/api/client";
import {
  Search,
  X,
  Loader2,
  Car,
  Wrench,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  ChevronRight,
  Info,
} from "lucide-react";

export type SearchRecordType =
  | "catalogue_part"
  | "marketplace_part"
  | "seller_part"
  | "admin_part"
  | "garage_vehicle"
  | "marketplace_vehicle"
  | "seller_vehicle"
  | "admin_vehicle";

export interface SearchResultItem {
  id: string;
  type: SearchRecordType;
  title: string;
  subtitle: string;
  sourceBadge: string;
  sourceBadgeColor: "amber" | "emerald" | "blue" | "purple" | "slate";
  identifierType: "MPN" | "VIN" | "PLATE";
  identifierValue: string;
  status?: string;
  price?: string | number;
  targetTab: string;
  rawItem: unknown;
}

interface GlobalSearchProps {
  onNavigate?: (tab: string, itemData?: { type: string; id: string; raw?: unknown }) => void;
  className?: string;
  autoFocus?: boolean;
  onClose?: () => void;
}

export default function GlobalSearch({
  onNavigate,
  className = "",
  autoFocus = false,
  onClose,
}: GlobalSearchProps) {
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [activeCategory, setActiveCategory] = useState<"all" | "parts" | "vehicles" | "orders">("all");
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeRole = user?.activeRole || (user?.rawRoles && user.rawRoles[0]) || "BUYER";
  const isAdmin = activeRole === "ADMIN" || activeRole === "STAFF" || user?.is_superuser || user?.is_staff;
  const isSeller = activeRole === "SELLER" || user?.rawRoles?.includes("SELLER");

  // Determine if query looks like an order number lookup
  const looksLikeOrderQuery = useCallback((q: string) => {
    const clean = q.trim().toUpperCase();
    return clean.includes("ORD") || clean.startsWith("DX-") || clean.startsWith("#") || /^ORD-\d+/i.test(clean);
  }, []);

  // Perform search across role-permitted live backend endpoints
  const performSearch = useCallback(
    async (searchTerm: string) => {
      const q = searchTerm.trim().toLowerCase();
      if (!q) {
        setResults([]);
        setIsLoading(false);
        setError(null);
        return;
      }

      setIsLoading(true);
      setError(null);

      const items: SearchResultItem[] = [];

      try {
        const promises: Promise<void>[] = [];

        // 1. Catalogue Parts by MPN / Name / Brand
        promises.push(
          api.catalogue
            .getParts({ search: q })
            .then((catalogueParts: PartSummary[]) => {
              catalogueParts.slice(0, 8).forEach((p) => {
                items.push({
                  id: p.id,
                  type: "catalogue_part",
                  title: `${p.brand ? `${p.brand} ` : ""}${p.name}`,
                  subtitle: p.category_name ? `Category: ${p.category_name}` : "OEM Reference Part",
                  sourceBadge: "Catalogue OEM",
                  sourceBadgeColor: "blue",
                  identifierType: "MPN",
                  identifierValue: p.mpn || "N/A",
                  targetTab: "catalogue",
                  rawItem: p,
                });
              });
            })
            .catch(() => {
              // Ignore partial failure to preserve other results
            })
        );

        // 2. Marketplace Live Approved Spare Parts by MPN / Name
        promises.push(
          api.marketplace
            .browseParts({ search: q })
            .then((marketParts: MarketplacePartListing[]) => {
              marketParts.slice(0, 8).forEach((p) => {
                items.push({
                  id: p.id,
                  type: "marketplace_part",
                  title: p.name,
                  subtitle: p.brand ? `Brand: ${p.brand} • ${p.condition}` : p.condition,
                  sourceBadge: "Marketplace Stock",
                  sourceBadgeColor: "emerald",
                  identifierType: "MPN",
                  identifierValue: p.mpn || "N/A",
                  price: p.price,
                  status: p.status,
                  targetTab: "marketplace_browse",
                  rawItem: p,
                });
              });
            })
            .catch(() => {})
        );

        // 3. Garage Vehicles by VIN, Plate, Make/Model
        promises.push(
          api.garage
            .listVehicles()
            .then((garageVehicles: GarageVehicle[]) => {
              const matched = garageVehicles.filter((v) => {
                const vinMatch = v.vin && v.vin.toLowerCase().includes(q);
                const plateMatch = v.registration_plate && v.registration_plate.toLowerCase().includes(q);
                const makeMatch = v.make && v.make.toLowerCase().includes(q);
                const modelMatch = v.model && v.model.toLowerCase().includes(q);
                const nickMatch = v.nickname && v.nickname.toLowerCase().includes(q);
                return vinMatch || plateMatch || makeMatch || modelMatch || nickMatch;
              });

              matched.slice(0, 6).forEach((v) => {
                items.push({
                  id: v.id,
                  type: "garage_vehicle",
                  title: `${v.year} ${v.make} ${v.model}`,
                  subtitle: v.nickname ? `"${v.nickname}" • ${v.trim || "Standard"}` : v.trim || "Personal Garage",
                  sourceBadge: "My Garage",
                  sourceBadgeColor: "amber",
                  identifierType: v.vin ? "VIN" : "PLATE",
                  identifierValue: v.vin || v.registration_plate || "UNSET",
                  status: v.is_primary ? "PRIMARY" : undefined,
                  targetTab: "garage",
                  rawItem: v,
                });
              });
            })
            .catch(() => {})
        );

        // 4. Marketplace Browse Vehicles (Public / Buyer)
        promises.push(
          api.marketplace
            .browseVehicles({ search: q })
            .then((browseVehicles: MarketplaceVehicleListing[]) => {
              browseVehicles.slice(0, 6).forEach((v) => {
                items.push({
                  id: v.id,
                  type: "marketplace_vehicle",
                  title: v.title || `${v.year} ${v.make_name || ""} ${v.model_name || ""}`,
                  subtitle: `${v.year} • ${v.fuel_type || "Petrol"} • ${v.transmission || "Manual"}`,
                  sourceBadge: "Marketplace Vehicle",
                  sourceBadgeColor: "emerald",
                  identifierType: "VIN",
                  identifierValue: v.masked_vin || (v as unknown as { vin?: string }).vin || "VERIFIED",
                  price: v.price,
                  status: v.status,
                  targetTab: "marketplace_browse",
                  rawItem: v,
                });
              });
            })
            .catch(() => {})
        );

        // 5. Role-Specific Queues: Admin Moderation (Admin/Staff only)
        if (isAdmin) {
          promises.push(
            api.marketplace
              .listAdminVehicles()
              .then((adminVehicles: MarketplaceVehicleListing[]) => {
                const matched = adminVehicles.filter((v) => {
                  const vinMatch = (v as unknown as { vin?: string }).vin?.toLowerCase().includes(q);
                  const titleMatch = v.title?.toLowerCase().includes(q);
                  const makeMatch = v.make_name?.toLowerCase().includes(q);
                  const modelMatch = v.model_name?.toLowerCase().includes(q);
                  return vinMatch || titleMatch || makeMatch || modelMatch;
                });
                matched.slice(0, 4).forEach((v) => {
                  items.push({
                    id: v.id,
                    type: "admin_vehicle",
                    title: v.title || `${v.year} ${v.make_name || ""} ${v.model_name || ""}`,
                    subtitle: `Seller: ${v.seller_name || v.seller || "Verified Seller"} • Status: ${v.status}`,
                    sourceBadge: "Admin Review Queue",
                    sourceBadgeColor: "purple",
                    identifierType: "VIN",
                    identifierValue: (v as unknown as { vin?: string }).vin || "N/A",
                    price: v.price,
                    status: v.status,
                    targetTab: "admin_marketplace_review",
                    rawItem: v,
                  });
                });
              })
              .catch(() => {})
          );

          promises.push(
            api.marketplace
              .listAdminParts()
              .then((adminParts: MarketplacePartListing[]) => {
                const matched = adminParts.filter((p) => {
                  const mpnMatch = p.mpn?.toLowerCase().includes(q);
                  const nameMatch = p.name?.toLowerCase().includes(q);
                  const brandMatch = p.brand?.toLowerCase().includes(q);
                  return mpnMatch || nameMatch || brandMatch;
                });
                matched.slice(0, 4).forEach((p) => {
                  items.push({
                    id: p.id,
                    type: "admin_part",
                    title: p.name,
                    subtitle: `Seller: ${p.seller_name || p.seller || "Verified Seller"} • ${p.brand || ""}`,
                    sourceBadge: "Admin Review Queue",
                    sourceBadgeColor: "purple",
                    identifierType: "MPN",
                    identifierValue: p.mpn || "N/A",
                    price: p.price,
                    status: p.status,
                    targetTab: "admin_marketplace_review",
                    rawItem: p,
                  });
                });
              })
              .catch(() => {})
          );
        }

        // 6. Role-Specific Queues: Seller Inventory (Seller only)
        if (isSeller && !isAdmin) {
          promises.push(
            api.marketplace
              .listMyVehicles()
              .then((myVehicles: MarketplaceVehicleListing[]) => {
                const matched = myVehicles.filter((v) => {
                  const vinMatch = (v as unknown as { vin?: string }).vin?.toLowerCase().includes(q);
                  const titleMatch = v.title?.toLowerCase().includes(q);
                  return vinMatch || titleMatch;
                });
                matched.slice(0, 4).forEach((v) => {
                  items.push({
                    id: v.id,
                    type: "seller_vehicle",
                    title: v.title,
                    subtitle: `My Inventory Vehicle • Status: ${v.status}`,
                    sourceBadge: "My Inventory",
                    sourceBadgeColor: "amber",
                    identifierType: "VIN",
                    identifierValue: (v as unknown as { vin?: string }).vin || "N/A",
                    price: v.price,
                    status: v.status,
                    targetTab: "seller_inventory",
                    rawItem: v,
                  });
                });
              })
              .catch(() => {})
          );

          promises.push(
            api.marketplace
              .listMyParts()
              .then((myParts: MarketplacePartListing[]) => {
                const matched = myParts.filter((p) => {
                  const mpnMatch = p.mpn?.toLowerCase().includes(q);
                  const nameMatch = p.name?.toLowerCase().includes(q);
                  return mpnMatch || nameMatch;
                });
                matched.slice(0, 4).forEach((p) => {
                  items.push({
                    id: p.id,
                    type: "seller_part",
                    title: p.name,
                    subtitle: `My Spare Part • Status: ${p.status}`,
                    sourceBadge: "My Inventory",
                    sourceBadgeColor: "amber",
                    identifierType: "MPN",
                    identifierValue: p.mpn || "N/A",
                    price: p.price,
                    status: p.status,
                    targetTab: "seller_inventory",
                    rawItem: p,
                  });
                });
              })
              .catch(() => {})
          );
        }

        await Promise.all(promises);

        // Sort results: prioritize exact identifier matches
        items.sort((a, b) => {
          const aExact = a.identifierValue.toLowerCase() === q;
          const bExact = b.identifierValue.toLowerCase() === q;
          if (aExact && !bExact) return -1;
          if (!aExact && bExact) return 1;
          return 0;
        });

        setResults(items);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Search query failed.");
      } finally {
        setIsLoading(false);
      }
    },
    [isAdmin, isSeller]
  );

  // Debounced search trigger (250ms)
  useEffect(() => {
    if (!query.trim()) return;

    const timer = setTimeout(() => {
      performSearch(query);
    }, 250);

    return () => clearTimeout(timer);
  }, [query, performSearch]);

  // Click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Keyboard shortcut listener (/ or Ctrl+K to focus search)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.key === "/" || (e.ctrlKey && e.key.toLowerCase() === "k")) && document.activeElement !== inputRef.current) {
        if (!["INPUT", "TEXTAREA", "SELECT"].includes((document.activeElement?.tagName || "").toUpperCase())) {
          e.preventDefault();
          inputRef.current?.focus();
          setIsOpen(true);
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Filter items by category tab
  const filteredResults = results.filter((item) => {
    if (activeCategory === "parts") {
      return item.identifierType === "MPN" || item.type.includes("part");
    }
    if (activeCategory === "vehicles") {
      return item.identifierType === "VIN" || item.identifierType === "PLATE" || item.type.includes("vehicle");
    }
    if (activeCategory === "orders") {
      return false; // Order listings not supported by backend
    }
    return true;
  });

  const partsCount = results.filter((r) => r.identifierType === "MPN" || r.type.includes("part")).length;
  const vehiclesCount = results.filter(
    (r) => r.identifierType === "VIN" || r.identifierType === "PLATE" || r.type.includes("vehicle")
  ).length;

  const handleSelectItem = (item: SearchResultItem) => {
    setIsOpen(false);
    if (onClose) onClose();
    if (onNavigate) {
      onNavigate(item.targetTab, {
        type: item.type,
        id: item.id,
        raw: item.rawItem,
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setIsOpen(false);
      inputRef.current?.blur();
      if (onClose) onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < filteredResults.length - 1 ? prev + 1 : prev));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1));
    } else if (e.key === "Enter") {
      if (selectedIndex >= 0 && selectedIndex < filteredResults.length) {
        e.preventDefault();
        handleSelectItem(filteredResults[selectedIndex]);
      }
    }
  };

  const getBadgeStyle = (color: SearchResultItem["sourceBadgeColor"]) => {
    switch (color) {
      case "amber":
        return "bg-amber-50 text-amber-800 border-amber-200";
      case "emerald":
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
      case "purple":
        return "bg-purple-50 text-purple-800 border-purple-200";
      case "blue":
      default:
        return "bg-blue-50 text-blue-800 border-blue-200";
    }
  };

  const showOrderNotice = activeCategory === "orders" || looksLikeOrderQuery(query);

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Search Input Bar */}
      <div className="flex items-center w-full h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs text-slate-900 focus-within:border-amber-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-amber-400/20 transition-all shadow-sm">
        <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          autoFocus={autoFocus}
          onChange={(e) => {
            const val = e.target.value;
            setQuery(val);
            setIsOpen(true);
            setSelectedIndex(-1);
            if (!val.trim()) {
              setResults([]);
              setIsLoading(false);
              setError(null);
            }
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search records by VIN, Order #, or Part MPN…"
          className="w-full bg-transparent focus:outline-none placeholder:text-slate-400 font-medium text-xs"
        />

        {isLoading ? (
          <Loader2 className="w-3.5 h-3.5 text-amber-500 animate-spin shrink-0 ml-2" />
        ) : query ? (
          <button
            onClick={() => {
              setQuery("");
              setResults([]);
              setIsOpen(false);
              inputRef.current?.focus();
            }}
            className="p-0.5 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-700 ml-1.5 transition-colors"
            title="Clear search"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        ) : (
          <span className="hidden xl:inline-block text-[10px] font-mono text-slate-400 bg-slate-200/60 px-1.5 py-0.5 rounded ml-2 select-none">
            /
          </span>
        )}
      </div>

      {/* Search Results Dropdown Popover */}
      {isOpen && query.trim().length > 0 && (
        <div className="absolute left-0 mt-2 w-[calc(100vw-2rem)] sm:w-[500px] md:w-[560px] lg:w-[620px] max-w-[92vw] bg-white rounded-2xl shadow-2xl border border-slate-200 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
          {/* Category Tabs Header */}
          <div className="p-2.5 bg-slate-50 border-b border-slate-200 flex items-center gap-1.5 overflow-x-auto text-xs">
            <button
              onClick={() => setActiveCategory("all")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-colors shrink-0 ${
                activeCategory === "all"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
              }`}
            >
              All Records ({results.length})
            </button>
            <button
              onClick={() => setActiveCategory("parts")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-colors flex items-center gap-1 shrink-0 ${
                activeCategory === "parts"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
              }`}
            >
              <Wrench className="w-3 h-3 text-amber-500" />
              <span>Parts (MPN)</span>
              {partsCount > 0 && (
                <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded-full bg-slate-200 text-slate-800 font-mono font-bold">
                  {partsCount}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveCategory("vehicles")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-colors flex items-center gap-1 shrink-0 ${
                activeCategory === "vehicles"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
              }`}
            >
              <Car className="w-3 h-3 text-blue-500" />
              <span>Vehicles (VIN)</span>
              {vehiclesCount > 0 && (
                <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded-full bg-slate-200 text-slate-800 font-mono font-bold">
                  {vehiclesCount}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveCategory("orders")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-colors flex items-center gap-1 shrink-0 ${
                activeCategory === "orders"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
              }`}
            >
              <Info className="w-3 h-3 text-amber-500" />
              <span>Order # Status</span>
            </button>
          </div>

          {/* Body Content */}
          <div className="max-h-[380px] overflow-y-auto p-2 divide-y divide-slate-100">
            {/* Loading Indicator */}
            {isLoading && results.length === 0 && (
              <div className="p-8 text-center text-slate-500">
                <Loader2 className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
                <p className="text-xs font-semibold">Searching live records across DriverXtra database...</p>
                <p className="text-[11px] text-slate-400 mt-1">Checking Garage VINs, Marketplace stock, and OEM Part MPNs.</p>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5 m-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="font-bold">Search request failed</div>
                  <div className="text-[11px] text-rose-700 mt-0.5">{error}</div>
                  <button
                    onClick={() => performSearch(query)}
                    className="mt-2 px-2.5 py-1 bg-white border border-rose-300 rounded font-bold text-[11px] text-rose-900 hover:bg-rose-100"
                  >
                    Retry Query
                  </button>
                </div>
              </div>
            )}

            {/* Order # Backend Limitation Notice */}
            {showOrderNotice && (
              <div className="p-3.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-950 text-xs m-2">
                <div className="flex items-center gap-2 font-bold text-amber-900 mb-1">
                  <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>Order # Search Limitation</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-black bg-amber-200 text-amber-900 border border-amber-300">
                    BACKEND UNSUPPORTED
                  </span>
                </div>
                <p className="text-[11px] text-amber-800 leading-relaxed">
                  The active DriverXtra backend implements real-time order creation and GST tax calculations (
                  <code className="bg-amber-100 px-1 py-0.2 rounded font-mono text-[10px]">/orders/checkout/</code>
                  ), but customer order tracking and order search endpoints are currently under active development.
                </p>
                <p className="text-[11px] text-slate-600 mt-1.5">
                  <span className="font-semibold text-slate-800">Available search capabilities:</span> Full VIN lookup across
                  personal garage and vehicle queues, plus instant Part MPN searches across the OEM parts catalogue and verified
                  seller inventory.
                </p>
              </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && filteredResults.length === 0 && activeCategory !== "orders" && (
              <div className="p-8 text-center text-slate-500">
                <HelpCircle className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-xs font-bold text-slate-800">No matching records found for &ldquo;{query}&rdquo;</p>
                <p className="text-[11px] text-slate-500 mt-1 max-w-sm mx-auto">
                  Try searching by a vehicle VIN (e.g. 17-character VIN or registration plate), or part MPN (e.g.{" "}
                  <span className="font-mono text-slate-700 bg-slate-100 px-1 py-0.5 rounded">BOSCH-0280140516</span> or{" "}
                  <span className="font-mono text-slate-700 bg-slate-100 px-1 py-0.5 rounded">BRK-4521</span>).
                </p>
              </div>
            )}

            {/* Matching Results List */}
            {filteredResults.map((item, idx) => {
              const isSelected = selectedIndex === idx;
              return (
                <div
                  key={`${item.type}-${item.id}`}
                  onClick={() => handleSelectItem(item)}
                  className={`p-2.5 rounded-xl cursor-pointer transition-all flex items-center justify-between gap-3 ${
                    isSelected ? "bg-amber-50/80 border border-amber-200" : "hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-start gap-2.5 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0 mt-0.5">
                      {item.identifierType === "MPN" ? (
                        <Wrench className="w-4 h-4 text-amber-600" />
                      ) : item.type.includes("admin") ? (
                        <ShieldCheck className="w-4 h-4 text-purple-600" />
                      ) : (
                        <Car className="w-4 h-4 text-blue-600" />
                      )}
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-bold text-slate-900 truncate">{item.title}</span>
                        <span
                          className={`text-[9px] font-bold px-1.5 py-0.2 rounded border ${getBadgeStyle(
                            item.sourceBadgeColor
                          )}`}
                        >
                          {item.sourceBadge}
                        </span>
                        {item.status && (
                          <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 border border-slate-200">
                            {item.status}
                          </span>
                        )}
                      </div>

                      <div className="text-[11px] text-slate-500 truncate mt-0.5">{item.subtitle}</div>

                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded border border-slate-200">
                          <span className="text-slate-400 font-semibold">{item.identifierType}:</span>
                          <span>{item.identifierValue}</span>
                        </span>

                        {item.price !== undefined && (
                          <span className="text-[11px] font-black text-slate-900">₹{Number(item.price).toLocaleString()}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 text-amber-600 text-[11px] font-bold shrink-0 opacity-80 group-hover:opacity-100">
                    <span className="hidden sm:inline">Open</span>
                    <ChevronRight className="w-4 h-4" />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer with Key Shortcuts and Context */}
          <div className="px-3.5 py-2 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-[10px] text-slate-500 font-medium">
            <div className="flex items-center gap-3">
              <span>
                <kbd className="font-mono bg-white border border-slate-200 px-1 rounded">↑</kbd>{" "}
                <kbd className="font-mono bg-white border border-slate-200 px-1 rounded">↓</kbd> to navigate
              </span>
              <span>
                <kbd className="font-mono bg-white border border-slate-200 px-1 rounded">Enter</kbd> to select
              </span>
              <span>
                <kbd className="font-mono bg-white border border-slate-200 px-1 rounded">Esc</kbd> to close
              </span>
            </div>
            <div className="text-slate-400">DriverXtra Live Records</div>
          </div>
        </div>
      )}
    </div>
  );
}
