"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  resolveMediaUrl,
  BuyerFavouriteVehicle,
  BuyerFavouritePart,
  MarketplaceVehicleListing,
  MarketplacePartListing,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Heart,
  Car,
  Wrench,
  Trash2,
  Eye,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  ShoppingBag,
  Gauge,
  Fuel,
  MapPin,
  ShieldCheck,
  X,
  XCircle,
  PackageCheck,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ImageIcon,
} from "lucide-react";

interface BuyerFavouritesViewProps {
  onNavigateToBrowse?: () => void;
}

type FilterTab = "ALL" | "VEHICLES" | "PARTS";

type UnifiedSavedItem =
  | {
      kind: "VEHICLE";
      id: string;
      createdAt: string;
      isAvailable: boolean;
      vehicle: MarketplaceVehicleListing;
      fav: BuyerFavouriteVehicle;
    }
  | {
      kind: "PART";
      id: string;
      createdAt: string;
      isAvailable: boolean;
      part: MarketplacePartListing;
      fav: BuyerFavouritePart;
    };

export default function BuyerFavouritesView({ onNavigateToBrowse }: BuyerFavouritesViewProps) {
  const { user } = useAuth();
  const [vehicleFavourites, setVehicleFavourites] = useState<BuyerFavouriteVehicle[]>([]);
  const [partFavourites, setPartFavourites] = useState<BuyerFavouritePart[]>([]);
  const [loading, setLoading] = useState(Boolean(user));
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [filterTab, setFilterTab] = useState<FilterTab>("ALL");

  // Inspect modals
  const [selectedVehicle, setSelectedVehicle] = useState<MarketplaceVehicleListing | null>(null);
  const [selectedVehicleImageIdx, setSelectedVehicleImageIdx] = useState<number>(0);
  const [selectedPart, setSelectedPart] = useState<MarketplacePartListing | null>(null);
  const [selectedPartImageIdx, setSelectedPartImageIdx] = useState<number>(0);

  const fetchFavourites = useCallback(() => {
    if (!user) {
      setVehicleFavourites([]);
      setPartFavourites([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    Promise.all([
      api.marketplace.listFavourites(),
      api.marketplace.listPartFavourites(),
    ])
      .then(([vehs, parts]) => {
        setVehicleFavourites(vehs);
        setPartFavourites(parts);
      })
      .catch((err: unknown) => {
        console.error("Failed to load saved items", err);
        const msg =
          err instanceof Error
            ? err.message
            : "Failed to load saved items. Please check your network connection.";
        setError(msg);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let ignore = false;

    Promise.all([
      api.marketplace.listFavourites(),
      api.marketplace.listPartFavourites(),
    ])
      .then(([vehs, parts]) => {
        if (!ignore) {
          setVehicleFavourites(vehs);
          setPartFavourites(parts);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          console.error("Failed to load saved items", err);
          const msg =
            err instanceof Error
              ? err.message
              : "Failed to load saved items. Please check your network connection.";
          setError(msg);
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [user]);

  const handleRemoveVehicle = async (favouriteId: string, vehicleTitle: string) => {
    if (removingId) return;
    setRemovingId(favouriteId);
    try {
      await api.marketplace.removeFavourite(favouriteId);
      setVehicleFavourites((prev) => prev.filter((f) => f.id !== favouriteId));
      if (selectedVehicle?.id === favouriteId) {
        setSelectedVehicle(null);
      }
    } catch (err: unknown) {
      console.error("Failed to remove favourite vehicle", err);
      const msg = err instanceof Error ? err.message : "Server error";
      alert(`Could not remove ${vehicleTitle} from saved items: ${msg}`);
    } finally {
      setRemovingId(null);
    }
  };

  const handleRemovePart = async (favouriteId: string, partName: string) => {
    if (removingId) return;
    setRemovingId(favouriteId);
    try {
      await api.marketplace.removePartFavourite(favouriteId);
      setPartFavourites((prev) => prev.filter((f) => f.id !== favouriteId));
      if (selectedPart?.id === favouriteId) {
        setSelectedPart(null);
      }
    } catch (err: unknown) {
      console.error("Failed to remove favourite part", err);
      const msg = err instanceof Error ? err.message : "Server error";
      alert(`Could not remove ${partName} from saved items: ${msg}`);
    } finally {
      setRemovingId(null);
    }
  };

  // Build unified items list
  const unifiedItems: UnifiedSavedItem[] = useMemo(() => {
    const list: UnifiedSavedItem[] = [];

    vehicleFavourites.forEach((fav) => {
      list.push({
        kind: "VEHICLE",
        id: fav.id,
        createdAt: fav.created_at,
        isAvailable: Boolean(fav.is_available && fav.vehicle?.status === "APPROVED"),
        vehicle: fav.vehicle,
        fav,
      });
    });

    partFavourites.forEach((fav) => {
      list.push({
        kind: "PART",
        id: fav.id,
        createdAt: fav.created_at,
        isAvailable: Boolean(fav.is_available && fav.part?.status === "APPROVED"),
        part: fav.part,
        fav,
      });
    });

    // Sort chronologically descending
    list.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    return list;
  }, [vehicleFavourites, partFavourites]);

  const filteredItems = useMemo(() => {
    if (filterTab === "VEHICLES") {
      return unifiedItems.filter((item) => item.kind === "VEHICLE");
    }
    if (filterTab === "PARTS") {
      return unifiedItems.filter((item) => item.kind === "PART");
    }
    return unifiedItems;
  }, [unifiedItems, filterTab]);

  const vehicleCount = vehicleFavourites.length;
  const partCount = partFavourites.length;
  const totalCount = vehicleCount + partCount;

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-200 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-black uppercase tracking-wider text-rose-700 bg-rose-100 px-2 py-0.5 rounded">
              Saved Items
            </span>
            <span className="text-xs text-slate-500">• Unified Vehicles & Spare Parts</span>
          </div>
          <h2 className="text-2xl font-black text-slate-950 mt-1">
            My Saved Items
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Keep track of approved vehicles and spare parts you are interested in purchasing on the marketplace.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchFavourites}
            disabled={loading}
            className="px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
            title="Refresh saved items"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          {onNavigateToBrowse && (
            <button
              onClick={onNavigateToBrowse}
              className="px-4 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-amber-400 text-xs font-bold flex items-center gap-1.5 shadow-xs transition-colors"
            >
              <ShoppingBag className="w-3.5 h-3.5" />
              <span>Browse Marketplace</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 p-1 bg-slate-200/80 rounded-2xl w-fit">
        <button
          type="button"
          onClick={() => setFilterTab("ALL")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            filterTab === "ALL"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <Boxes className="w-3.5 h-3.5 text-amber-500" />
          <span>All Saved Items</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "ALL"
                ? "bg-slate-900 text-white"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {totalCount}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setFilterTab("VEHICLES")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            filterTab === "VEHICLES"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <Car className="w-3.5 h-3.5 text-indigo-500" />
          <span>Vehicles</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "VEHICLES"
                ? "bg-indigo-600 text-white"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {vehicleCount}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setFilterTab("PARTS")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            filterTab === "PARTS"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <Wrench className="w-3.5 h-3.5 text-amber-500" />
          <span>Spare Parts</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "PARTS"
                ? "bg-amber-600 text-white"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {partCount}
          </span>
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl flex items-center justify-between text-xs text-rose-900">
          <div className="flex items-center gap-2">
            <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchFavourites}
            className="px-3 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-bold text-xs"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="py-24 text-center space-y-3">
          <div className="w-8 h-8 border-2 border-rose-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs text-slate-500 font-medium">Loading your saved items...</p>
        </div>
      ) : filteredItems.length === 0 ? (
        /* Empty State */
        <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center max-w-lg mx-auto space-y-4 shadow-xs">
          <div className="w-16 h-16 rounded-full bg-rose-50 border border-rose-100 flex items-center justify-center mx-auto text-rose-500">
            {filterTab === "VEHICLES" ? (
              <Car className="w-8 h-8 text-indigo-500" />
            ) : filterTab === "PARTS" ? (
              <Wrench className="w-8 h-8 text-amber-500" />
            ) : (
              <Heart className="w-8 h-8 text-rose-500" />
            )}
          </div>
          <div>
            <h3 className="text-lg font-black text-slate-900">
              {filterTab === "VEHICLES"
                ? "No Saved Vehicles"
                : filterTab === "PARTS"
                ? "No Saved Spare Parts"
                : "No Saved Items Yet"}
            </h3>
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              {filterTab === "VEHICLES"
                ? "You haven't saved any vehicles yet. Explore approved vehicles on the marketplace and click the heart icon to save them."
                : filterTab === "PARTS"
                ? "You haven't saved any spare parts yet. Explore verified spare parts on the marketplace and click the heart icon to save them."
                : "When browsing vehicles or spare parts on the marketplace, click the heart icon on any card to save it to your personal list."}
            </p>
          </div>
          {onNavigateToBrowse && (
            <button
              onClick={onNavigateToBrowse}
              className="px-5 py-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 text-amber-400 font-bold text-xs inline-flex items-center gap-2 shadow-xs transition-colors"
            >
              <ShoppingBag className="w-4 h-4" />
              <span>Browse Marketplace</span>
            </button>
          )}
        </div>
      ) : (
        /* Unified Saved Items Grid */
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
            <span>
              Showing {filteredItems.length}{" "}
              {filterTab === "VEHICLES"
                ? filteredItems.length === 1
                  ? "vehicle"
                  : "vehicles"
                : filterTab === "PARTS"
                ? filteredItems.length === 1
                  ? "spare part"
                  : "spare parts"
                : filteredItems.length === 1
                ? "item"
                : "items"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredItems.map((item) => {
              if (item.kind === "VEHICLE") {
                const v = item.vehicle;
                const isAvailable = item.isAvailable;
                const isRemoving = removingId === item.id;

                return (
                  <div
                    key={`vehicle-${item.id}`}
                    className={`bg-white rounded-3xl border overflow-hidden shadow-xs hover:shadow-md transition-all flex flex-col justify-between ${
                      isAvailable ? "border-slate-200" : "border-amber-300/80 bg-amber-50/20"
                    }`}
                  >
                    <div>
                      {/* Image / Header Banner */}
                      <div className="relative h-44 bg-slate-950 flex items-center justify-center overflow-hidden">
                        {v?.primary_image_url ? (
                          <img
                            src={resolveMediaUrl(v.primary_image_url)}
                            alt={v.title || "Vehicle"}
                            className={`w-full h-full object-cover transition-opacity ${
                              isAvailable ? "" : "opacity-60 grayscale"
                            }`}
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                              const fb = e.currentTarget.parentElement?.querySelector(".fav-vehicle-card-fallback");
                              if (fb) (fb as HTMLElement).style.display = "flex";
                            }}
                          />
                        ) : null}
                        <div
                          className={`fav-vehicle-card-fallback text-center p-4 items-center justify-center flex-col ${
                            v?.primary_image_url ? "hidden" : "flex"
                          }`}
                        >
                          <Car className="w-12 h-12 text-slate-700 mx-auto mb-1" />
                          <span className="text-[10px] text-slate-500 font-medium">Verified Dealer Vehicle</span>
                        </div>

                        {/* Top Left Badges: Item Type & Status */}
                        <div className="absolute top-3 left-3 flex flex-col items-start gap-1.5">
                          <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-600/90 text-white text-[10px] font-bold shadow-xs">
                            <Car className="w-3 h-3" />
                            <span>Vehicle</span>
                          </span>
                          {isAvailable ? (
                            <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-900/80 backdrop-blur-md text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>Verified Active</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950/90 backdrop-blur-md text-[10px] font-bold text-amber-300 border border-amber-400/30">
                              <AlertTriangle className="w-3 h-3" />
                              <span>Listing Unavailable</span>
                            </div>
                          )}
                        </div>

                        {/* Remove Favourite Button */}
                        <button
                          type="button"
                          onClick={() => handleRemoveVehicle(item.id, v?.title || "vehicle")}
                          disabled={isRemoving}
                          aria-label={`Remove ${v?.title || "vehicle"} from saved items`}
                          className="absolute top-3 right-3 p-2 rounded-full bg-slate-900/80 hover:bg-rose-600 text-rose-400 hover:text-white backdrop-blur-md transition-all border border-slate-700/60 shadow-md focus:outline-hidden focus:ring-2 focus:ring-rose-400 disabled:opacity-50"
                          title="Remove from saved items"
                        >
                          {isRemoving ? (
                            <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>

                        {/* Price Badge */}
                        {v && (
                          <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-xl bg-slate-950/90 text-white font-black text-sm">
                            £{Number(v.price).toLocaleString()}
                          </div>
                        )}
                      </div>

                      {/* Content */}
                      <div className="p-5 space-y-3">
                        <div>
                          <div className="text-[11px] font-bold text-amber-600 uppercase tracking-wider">
                            {v?.year} · {v?.make_name} {v?.model_name}
                          </div>
                          <h4 className="text-sm font-black text-slate-900 line-clamp-1">
                            {v?.title || "Vehicle Listing"}
                          </h4>
                        </div>

                        {/* Unavailable Notice */}
                        {!isAvailable && (
                          <div className="p-2.5 bg-amber-50 rounded-xl border border-amber-200 text-[11px] text-amber-900 leading-snug">
                            <strong>Note:</strong> This vehicle is currently inactive or under review and is no longer public for sale.
                          </div>
                        )}

                        {/* Specs */}
                        {v && (
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
                        )}

                        {/* Seller Tag */}
                        {v && (
                          <div className="flex items-center justify-between text-[11px] text-slate-500">
                            <span>
                              Seller: <strong className="text-slate-800">{v.organisation_name || v.seller_name || "Verified Trader"}</strong>
                            </span>
                            <span className="font-mono text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">
                              {v.masked_registration || "Verified"}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="p-5 pt-0 flex gap-2">
                      {v && (
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedVehicle(v);
                            setSelectedVehicleImageIdx(0);
                          }}
                          className="flex-1 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5"
                        >
                          <Eye className="w-3.5 h-3.5 text-amber-400" />
                          <span>Inspect Details</span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleRemoveVehicle(item.id, v?.title || "vehicle")}
                        disabled={isRemoving}
                        aria-label="Remove favourite"
                        className="px-3.5 py-2.5 bg-slate-100 hover:bg-rose-50 text-slate-600 hover:text-rose-600 text-xs font-bold rounded-xl transition-colors flex items-center justify-center"
                        title="Remove from saved items"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              }

              // Spare Part Item
              const p = item.part;
              const isAvailable = item.isAvailable;
              const isRemoving = removingId === item.id;

              return (
                <div
                  key={`part-${item.id}`}
                  className={`bg-white rounded-3xl border overflow-hidden shadow-xs hover:shadow-md transition-all flex flex-col justify-between ${
                    isAvailable ? "border-slate-200" : "border-amber-300/80 bg-amber-50/20"
                  }`}
                >
                  <div>
                    {/* Image / Header Banner */}
                    <div className="relative h-44 bg-slate-950 flex items-center justify-center overflow-hidden">
                      {p?.primary_image_url ? (
                        <img
                          src={resolveMediaUrl(p.primary_image_url)}
                          alt={p.name || "Spare Part"}
                          className={`w-full h-full object-cover transition-opacity ${
                            isAvailable ? "" : "opacity-60 grayscale"
                          }`}
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
                            const fb = e.currentTarget.parentElement?.querySelector(".fav-part-card-fallback");
                            if (fb) (fb as HTMLElement).style.display = "flex";
                          }}
                        />
                      ) : null}
                      <div
                        className={`fav-part-card-fallback text-center p-4 items-center justify-center flex-col ${
                          p?.primary_image_url ? "hidden" : "flex"
                        }`}
                      >
                        <Wrench className="w-12 h-12 text-slate-700 mx-auto mb-1" />
                        <span className="text-[10px] text-slate-500 font-medium">Verified Dealer Part</span>
                      </div>

                      {/* Top Left Badges: Item Type & Status */}
                      <div className="absolute top-3 left-3 flex flex-col items-start gap-1.5">
                        <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-600/90 text-white text-[10px] font-bold shadow-xs">
                          <Wrench className="w-3 h-3" />
                          <span>Spare Part</span>
                        </span>
                        {isAvailable ? (
                          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-900/80 backdrop-blur-md text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
                            <CheckCircle2 className="w-3 h-3" />
                            <span>Verified Active</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950/90 backdrop-blur-md text-[10px] font-bold text-amber-300 border border-amber-400/30">
                            <AlertTriangle className="w-3 h-3" />
                            <span>Listing Unavailable</span>
                          </div>
                        )}
                      </div>

                      {/* Remove Favourite Button */}
                      <button
                        type="button"
                        onClick={() => handleRemovePart(item.id, p?.name || "spare part")}
                        disabled={isRemoving}
                        aria-label={`Remove ${p?.name || "spare part"} from saved items`}
                        className="absolute top-3 right-3 p-2 rounded-full bg-slate-900/80 hover:bg-rose-600 text-rose-400 hover:text-white backdrop-blur-md transition-all border border-slate-700/60 shadow-md focus:outline-hidden focus:ring-2 focus:ring-rose-400 disabled:opacity-50"
                        title="Remove from saved items"
                      >
                        {isRemoving ? (
                          <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                      </button>

                      {/* Price Badge */}
                      {p && (
                        <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-xl bg-slate-950/90 text-white font-black text-sm">
                          £{Number(p.price).toFixed(2)}
                        </div>
                      )}
                    </div>

                    {/* Content */}
                    <div className="p-5 space-y-3">
                      <div>
                        <div className="text-[11px] font-bold text-amber-600 uppercase tracking-wider">
                          {p?.brand} · MPN: {p?.mpn}
                        </div>
                        <h4 className="text-sm font-black text-slate-900 line-clamp-1">
                          {p?.name || "Spare Part Listing"}
                        </h4>
                      </div>

                      {/* Unavailable Notice */}
                      {!isAvailable && (
                        <div className="p-2.5 bg-amber-50 rounded-xl border border-amber-200 text-[11px] text-amber-900 leading-snug">
                          <strong>Note:</strong> This spare part is currently inactive or under review and is no longer public for sale.
                        </div>
                      )}

                      {/* Specs */}
                      {p && (
                        <div className="grid grid-cols-3 gap-2 py-2 border-y border-slate-100 text-[11px]">
                          <div className="flex flex-col text-slate-600">
                            <span className="text-[10px] text-slate-400">Category</span>
                            <span className="font-bold text-slate-800 truncate">{p.category_name || "General"}</span>
                          </div>
                          <div className="flex flex-col text-slate-600">
                            <span className="text-[10px] text-slate-400">Condition</span>
                            <span className="font-bold text-slate-800">{p.condition}</span>
                          </div>
                          <div className="flex flex-col text-slate-600">
                            <span className="text-[10px] text-slate-400">Stock</span>
                            <span
                              className={`font-bold ${
                                p.stock_quantity === 0 || p.availability === "OUT_OF_STOCK"
                                  ? "text-rose-600"
                                  : "text-emerald-700"
                              }`}
                            >
                              {p.stock_quantity > 0 ? `${p.stock_quantity} left` : "Out of stock"}
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Seller Tag */}
                      {p && (
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>
                            Seller: <strong className="text-slate-800">{p.organisation_name || p.seller_name || "Verified Trader"}</strong>
                          </span>
                          {p.compatible_variants && p.compatible_variants.length > 0 && (
                            <span className="font-bold text-emerald-700 text-[10px] bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                              {p.compatible_variants.length} Fits
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="p-5 pt-0 flex gap-2">
                    {p && (
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedPart(p);
                          setSelectedPartImageIdx(0);
                        }}
                        className="flex-1 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5"
                      >
                        <Eye className="w-3.5 h-3.5 text-amber-400" />
                        <span>Inspect Details</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleRemovePart(item.id, p?.name || "spare part")}
                      disabled={isRemoving}
                      aria-label="Remove favourite"
                      className="px-3.5 py-2.5 bg-slate-100 hover:bg-rose-50 text-slate-600 hover:text-rose-600 text-xs font-bold rounded-xl transition-colors flex items-center justify-center"
                      title="Remove from saved items"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Vehicle Inspector Modal */}
      {selectedVehicle && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200">
                  Approved Marketplace Vehicle
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">{selectedVehicle.title}</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedVehicle(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
                aria-label="Close inspector"
              >
                <X className="w-5 h-5" />
              </button>
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
                  <div className="relative rounded-2xl overflow-hidden h-64 bg-slate-950 flex items-center justify-center">
                    <img
                      src={resolveMediaUrl(activeImage)}
                      alt={`${selectedVehicle.title} - photo ${activeIdx + 1}`}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        const fb = e.currentTarget.parentElement?.querySelector(".fav-gallery-vehicle-fallback");
                        if (fb) (fb as HTMLElement).style.display = "flex";
                      }}
                    />
                    <div className="fav-gallery-vehicle-fallback hidden flex-col items-center justify-center text-slate-500 p-6 text-center">
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
                <span className="text-[10px] text-slate-500">Year / Model</span>
                <p className="font-bold text-slate-900 mt-0.5">
                  {selectedVehicle.year} {selectedVehicle.model_name}
                </p>
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
                type="button"
                onClick={() => setSelectedVehicle(null)}
                className="px-5 py-2.5 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Spare Part Inspector Modal */}
      {selectedPart && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  Approved Spare Part
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">{selectedPart.name}</h3>
                <p className="text-xs text-slate-500 font-mono">
                  {selectedPart.brand} · MPN: {selectedPart.mpn}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedPart(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
                aria-label="Close inspector"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

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
                        const fb = e.currentTarget.parentElement?.querySelector(".fav-gallery-part-fallback");
                        if (fb) (fb as HTMLElement).style.display = "flex";
                      }}
                    />
                    <div className="fav-gallery-part-fallback hidden flex-col items-center justify-center text-slate-500 p-6 text-center">
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

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Retail Price</span>
                <p className="font-black text-sm text-slate-950 mt-0.5">
                  £{Number(selectedPart.price).toFixed(2)}
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Brand / MPN</span>
                <p className="font-bold text-slate-900 mt-0.5 truncate">
                  {selectedPart.brand}
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Category</span>
                <p className="font-bold text-slate-900 mt-0.5 truncate">
                  {selectedPart.category_name || "General"}
                </p>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-500">Condition</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedPart.condition}</p>
              </div>
            </div>

            {/* Stock Availability status */}
            <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PackageCheck className="w-4 h-4 text-emerald-600" />
                <span className="font-bold text-slate-800">Stock Availability:</span>
              </div>
              <span
                className={`font-bold px-2 py-0.5 rounded-full text-xs ${
                  selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"
                    ? "bg-rose-100 text-rose-700"
                    : selectedPart.stock_quantity <= (selectedPart.low_stock_threshold ?? 3)
                    ? "bg-amber-100 text-amber-700"
                    : "bg-emerald-100 text-emerald-700"
                }`}
              >
                {selectedPart.stock_quantity === 0 || selectedPart.availability === "OUT_OF_STOCK"
                  ? "Out of Stock"
                  : `${selectedPart.stock_quantity} Units Available`}
              </span>
            </div>

            {/* OEM Numbers */}
            {selectedPart.oem_numbers && selectedPart.oem_numbers.length > 0 && (
              <div className="space-y-1 text-xs">
                <h5 className="font-bold text-slate-800">OEM Cross References</h5>
                <div className="flex flex-wrap gap-2">
                  {selectedPart.oem_numbers.map((oem, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-1 bg-slate-100 border border-slate-200 text-slate-800 font-mono text-[11px] rounded-lg"
                    >
                      {oem}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Compatible Variants */}
            {selectedPart.compatible_variants && selectedPart.compatible_variants.length > 0 && (
              <div className="space-y-1 text-xs">
                <h5 className="font-bold text-slate-800">
                  Verified Compatible Variants ({selectedPart.compatible_variants.length})
                </h5>
                <div className="max-h-32 overflow-y-auto space-y-1 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                  {selectedPart.compatible_variants.map((v) => (
                    <div key={v.id} className="text-[11px] text-slate-700">
                      • {v.display_name || `${v.year || ""} ${v.engine_code || ""}`}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedPart.description && (
              <div className="space-y-1 text-xs">
                <h5 className="font-bold text-slate-800">Seller Description</h5>
                <p className="text-slate-600 whitespace-pre-line leading-relaxed bg-slate-50 p-3.5 rounded-2xl border border-slate-100">
                  {selectedPart.description}
                </p>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                type="button"
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
