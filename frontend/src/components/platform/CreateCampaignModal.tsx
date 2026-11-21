"use client";

import React, { useState, useEffect } from "react";
import {
  api,
  AdvertisingCampaign,
  CampaignType,
  CampaignPricingQuote,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  resolveMediaUrl,
} from "@/lib/api/client";
import {
  X,
  Megaphone,
  Check,
  ChevronRight,
  ChevronLeft,
  Calendar,
  DollarSign,
  Layers,
  Sparkles,
  Info,
  AlertCircle,
  Loader2,
  Car,
  Wrench,
  Search,
  CheckCircle2,
  Clock,
  ArrowRight,
} from "lucide-react";

interface CreateCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (campaign: AdvertisingCampaign) => void;
  initialType?: CampaignType;
}

interface SelectableInventoryItem {
  id: string;
  title?: string;
  name?: string;
  make?: string;
  model?: string;
  currency?: string;
  price?: number;
  part?: { name?: string };
  images?: Array<{ image?: string }>;
  [key: string]: unknown;
}

export default function CreateCampaignModal({
  isOpen,
  onClose,
  onSuccess,
  initialType = "VEHICLES",
}: CreateCampaignModalProps) {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Form State
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [campaignType, setCampaignType] = useState<CampaignType>(initialType);
  const [targetCountry, setTargetCountry] = useState<"GB" | "IN">("GB");
  const [currency, setCurrency] = useState<"GBP" | "INR">("GBP");
  const [packageCode, setPackageCode] = useState<"7_DAYS" | "14_DAYS" | "30_DAYS" | "CUSTOM">("7_DAYS");
  const [customDurationDays, setCustomDurationDays] = useState<number>(7);
  const [startDate, setStartDate] = useState<string>(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split("T")[0];
  });

  // Selected Listings
  const [availableListings, setAvailableListings] = useState<SelectableInventoryItem[]>([]);
  const [selectedListingIds, setSelectedListingIds] = useState<string[]>([]);
  const [loadingListings, setLoadingListings] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Dynamic Quote
  const [quote, setQuote] = useState<CampaignPricingQuote | null>(null);
  const [loadingQuote, setLoadingQuote] = useState(false);

  // Submission
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Sync currency with country
  useEffect(() => {
    if (targetCountry === "GB") {
      setCurrency("GBP");
    } else {
      setCurrency("INR");
    }
  }, [targetCountry]);

  // Fetch approved listings when entering Step 2 or changing campaignType
  useEffect(() => {
    if (!isOpen) return;
    async function loadListings() {
      setLoadingListings(true);
      setErrorMsg(null);
      try {
        if (campaignType === "VEHICLES") {
          const items = await api.marketplace.listMyVehicles("APPROVED");
          setAvailableListings((items as unknown as SelectableInventoryItem[]) || []);
        } else {
          const items = await api.marketplace.listMyParts("APPROVED");
          setAvailableListings((items as unknown as SelectableInventoryItem[]) || []);
        }
      } catch (err: unknown) {
        console.error("Failed to load approved listings", err);
        setErrorMsg("Failed to load approved inventory. Only approved listings can be sponsored.");
      } finally {
        setLoadingListings(false);
      }
    }
    loadListings();
  }, [isOpen, campaignType]);

  // Fetch dynamic quote when package or duration or currency changes
  useEffect(() => {
    async function fetchQuote() {
      setLoadingQuote(true);
      try {
        const q = await api.marketplace.getAdvertisingQuote({
          currency,
          package_code: packageCode,
          duration_days: packageCode === "CUSTOM" ? customDurationDays : undefined,
          target_country: targetCountry,
        });
        setQuote(q);
      } catch (err: unknown) {
        console.error("Failed to calculate quote", err);
      } finally {
        setLoadingQuote(false);
      }
    }
    fetchQuote();
  }, [currency, packageCode, customDurationDays, targetCountry]);

  if (!isOpen) return null;

  const toggleSelectListing = (id: string) => {
    if (selectedListingIds.includes(id)) {
      setSelectedListingIds(selectedListingIds.filter((item) => item !== id));
    } else {
      setSelectedListingIds([...selectedListingIds, id]);
    }
  };

  const selectAllFiltered = () => {
    const ids = filteredListings.map((l) => l.id);
    setSelectedListingIds(Array.from(new Set([...selectedListingIds, ...ids])));
  };

  const deselectAll = () => {
    setSelectedListingIds([]);
  };

  const filteredListings = availableListings.filter((l) => {
    const q = searchQuery.toLowerCase();
    const titleText = l.title || ((l.make || l.model) ? `${l.make || ""} ${l.model || ""}` : (l.part?.name || l.name || ""));
    return String(titleText).toLowerCase().includes(q);
  });

  const handleNext = () => {
    setErrorMsg(null);
    if (step === 1) {
      if (!title.trim()) {
        setErrorMsg("Please enter a campaign title.");
        return;
      }
      setStep(2);
    } else if (step === 2) {
      if (selectedListingIds.length === 0) {
        setErrorMsg("Please select at least one approved listing to sponsor.");
        return;
      }
      setStep(3);
    } else if (step === 3) {
      if (packageCode === "CUSTOM" && (customDurationDays < 3 || customDurationDays > 90)) {
        setErrorMsg("Custom campaign duration must be between 3 and 90 days.");
        return;
      }
      setStep(4);
    }
  };

  const handleSubmit = async (submitForReview: boolean) => {
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const campaign = await api.marketplace.createAdvertisingCampaign({
        title: title.trim(),
        description: description.trim(),
        campaign_type: campaignType,
        target_country: targetCountry,
        currency,
        package_code: packageCode,
        duration_days: packageCode === "CUSTOM" ? customDurationDays : undefined,
        start_date: startDate || null,
        listing_ids: selectedListingIds,
        submit_for_review: submitForReview,
      });

      onSuccess(campaign);
      onClose();
    } catch (err: unknown) {
      console.error("Campaign creation error", err);
      const detail = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to create advertising campaign.");
      setErrorMsg(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-400/10 border border-amber-400/30 flex items-center justify-center text-amber-400">
              <Megaphone className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Create Sponsored Ad Campaign</h2>
              <p className="text-xs text-slate-400">Promote your vehicle or spare part listings at top marketplace placements</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Stepper Progress */}
        <div className="px-6 py-3 bg-slate-950/30 border-b border-slate-800/80 flex items-center justify-between text-xs">
          {[
            { num: 1, label: "Campaign Details" },
            { num: 2, label: "Select Listings" },
            { num: 3, label: "Duration & Budget" },
            { num: 4, label: "Review & Confirm" },
          ].map((item, idx) => (
            <div key={item.num} className="flex items-center gap-2">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                  step === item.num
                    ? "bg-amber-400 text-slate-950 ring-2 ring-amber-400/30"
                    : step > item.num
                    ? "bg-emerald-500 text-slate-950"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {step > item.num ? <Check className="w-3.5 h-3.5 stroke-[3]" /> : item.num}
              </div>
              <span
                className={`hidden sm:inline font-medium ${
                  step === item.num ? "text-amber-400" : step > item.num ? "text-slate-200" : "text-slate-500"
                }`}
              >
                {item.label}
              </span>
              {idx < 3 && <ChevronRight className="w-4 h-4 text-slate-700 ml-1 hidden sm:inline" />}
            </div>
          ))}
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {errorMsg && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm flex items-start gap-3">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* STEP 1: Details */}
          {step === 1 && (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Campaign Title <span className="text-amber-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Premium SUV Spring Showcase 2026"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-amber-400 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Campaign Description (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="Internal notes or goals for this campaign..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-amber-400 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    Inventory Type <span className="text-amber-400">*</span>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setCampaignType("VEHICLES");
                        setSelectedListingIds([]);
                      }}
                      className={`p-3 rounded-xl border flex flex-col items-center gap-1.5 transition text-left ${
                        campaignType === "VEHICLES"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <Car className="w-5 h-5" />
                      <span className="text-xs font-semibold">Vehicles</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setCampaignType("SPARE_PARTS");
                        setSelectedListingIds([]);
                      }}
                      className={`p-3 rounded-xl border flex flex-col items-center gap-1.5 transition text-left ${
                        campaignType === "SPARE_PARTS"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <Wrench className="w-5 h-5" />
                      <span className="text-xs font-semibold">Spare Parts</span>
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    Target Market & Tax Regime <span className="text-amber-400">*</span>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setTargetCountry("GB")}
                      className={`p-3 rounded-xl border flex flex-col items-center gap-1 transition ${
                        targetCountry === "GB"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <span className="text-xs font-bold">United Kingdom (GB)</span>
                      <span className="text-[10px] text-slate-500">GBP • 20% VAT</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setTargetCountry("IN")}
                      className={`p-3 rounded-xl border flex flex-col items-center gap-1 transition ${
                        targetCountry === "IN"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <span className="text-xs font-bold">India (IN)</span>
                      <span className="text-[10px] text-slate-500">INR • 18% GST</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: Listing Selection */}
          {step === 2 && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">
                    Select {campaignType === "VEHICLES" ? "Vehicle" : "Spare Part"} Listings
                  </h3>
                  <p className="text-xs text-slate-400">
                    Selected: <span className="text-amber-400 font-bold">{selectedListingIds.length}</span> items
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={selectAllFiltered}
                    className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={deselectAll}
                    className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
                  >
                    Clear Selection
                  </button>
                </div>
              </div>

              {/* Search input */}
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
                <input
                  type="text"
                  placeholder="Filter by title, make or model..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-amber-400 text-xs"
                />
              </div>

              {loadingListings ? (
                <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-3">
                  <Loader2 className="w-6 h-6 animate-spin text-amber-400" />
                  <span className="text-xs">Loading approved inventory...</span>
                </div>
              ) : filteredListings.length === 0 ? (
                <div className="py-10 text-center rounded-xl border border-dashed border-slate-800 text-slate-500 text-xs">
                  No approved {campaignType.toLowerCase()} found matching your filter. Ensure listings are APPROVED by staff before sponsoring.
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {filteredListings.map((item) => {
                    const isSelected = selectedListingIds.includes(item.id);
                    const titleStr = item.title || ((item.make || item.model) ? `${item.make || ""} ${item.model || ""}` : (item.part?.name || item.name || "Inventory Item"));
                    const priceStr = item.price ? `${item.currency || currency} ${Number(item.price).toLocaleString()}` : "Price On Request";
                    const firstImg = item.images?.[0];
                    const imgUrl = (firstImg && typeof firstImg === "object" && typeof firstImg.image === "string") ? resolveMediaUrl(firstImg.image) : null;

                    return (
                      <div
                        key={item.id}
                        onClick={() => toggleSelectListing(item.id)}
                        className={`p-3 rounded-xl border cursor-pointer flex items-center justify-between gap-3 transition ${
                          isSelected
                            ? "bg-amber-400/10 border-amber-400/60"
                            : "bg-slate-950/60 border-slate-800 hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-5 h-5 rounded flex items-center justify-center border transition ${
                              isSelected
                                ? "bg-amber-400 border-amber-400 text-slate-950"
                                : "border-slate-700 bg-slate-900"
                            }`}
                          >
                            {isSelected && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                          </div>

                          <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center text-slate-500">
                            {imgUrl ? (
                              <img src={imgUrl} alt={titleStr} className="w-full h-full object-cover" />
                            ) : campaignType === "VEHICLES" ? (
                              <Car className="w-5 h-5" />
                            ) : (
                              <Wrench className="w-5 h-5" />
                            )}
                          </div>

                          <div>
                            <p className="text-xs font-semibold text-white line-clamp-1">{titleStr}</p>
                            <p className="text-[11px] text-slate-400">{priceStr}</p>
                          </div>
                        </div>

                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          APPROVED
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* STEP 3: Duration & Budget */}
          {step === 3 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                  Select Advertising Package
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  {[
                    { code: "7_DAYS", label: "7 Days", desc: "Short-term burst", badge: "Popular" },
                    { code: "14_DAYS", label: "14 Days", desc: "Balanced campaign", badge: "14% Off" },
                    { code: "30_DAYS", label: "30 Days", desc: "Maximum visibility", badge: "27% Off" },
                    { code: "CUSTOM", label: "Custom", desc: "3 to 90 days", badge: "Flexible" },
                  ].map((pkg) => (
                    <button
                      key={pkg.code}
                      type="button"
                      onClick={() => setPackageCode(pkg.code as "7_DAYS" | "14_DAYS" | "30_DAYS" | "CUSTOM")}
                      className={`p-3.5 rounded-xl border text-left flex flex-col justify-between transition ${
                        packageCode === pkg.code
                          ? "bg-amber-400/10 border-amber-400 ring-1 ring-amber-400"
                          : "bg-slate-950 border-slate-800 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white">{pkg.label}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-400/20 text-amber-300 font-semibold">
                          {pkg.badge}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400 mt-2">{pkg.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {packageCode === "CUSTOM" && (
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-400">Custom Duration (Days):</span>
                    <span className="font-bold text-amber-400">{customDurationDays} Days</span>
                  </div>
                  <input
                    type="range"
                    min={3}
                    max={90}
                    value={customDurationDays}
                    onChange={(e) => setCustomDurationDays(Number(e.target.value))}
                    className="w-full accent-amber-400 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500">
                    <span>3 Days Min</span>
                    <span>90 Days Max</span>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Campaign Start Date
                </label>
                <div className="relative">
                  <Calendar className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
                  <input
                    type="date"
                    value={startDate}
                    min={new Date().toISOString().split("T")[0]}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-amber-400 text-xs"
                  />
                </div>
              </div>

              {/* Dynamic Quote Card */}
              {loadingQuote ? (
                <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center gap-2 text-slate-400 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
                  <span>Computing official statutory tax quote...</span>
                </div>
              ) : quote ? (
                <div className="p-5 rounded-xl bg-gradient-to-br from-slate-950 to-slate-900 border border-amber-400/20 space-y-3">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs">
                    <span className="text-slate-400">Duration</span>
                    <span className="font-bold text-white">{quote.duration_days} Days</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">Net Advertising Fee</span>
                    <span className="font-semibold text-slate-200">
                      {currency} {(quote.net_amount_minor / 100).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">
                      {quote.tax_regime} ({quote.tax_rate_percent}%)
                      {quote.sac_code ? ` [SAC ${quote.sac_code}]` : ""}
                    </span>
                    <span className="font-semibold text-slate-200">
                      {currency} {(quote.tax_amount_minor / 100).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                    <div>
                      <span className="text-xs font-bold text-white">Total Ad Spend</span>
                      <p className="text-[10px] text-slate-500">
                        Daily Rate: {currency} {(quote.daily_rate_minor / 100).toFixed(2)} / day
                      </p>
                    </div>
                    <span className="text-lg font-black text-amber-400">
                      {currency} {(quote.total_amount_minor / 100).toFixed(2)}
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {/* STEP 4: Review & Confirm */}
          {step === 4 && (
            <div className="space-y-5 animate-in fade-in duration-200 text-xs">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <h4 className="font-bold text-white text-sm">Campaign Summary</h4>
                <div className="grid grid-cols-2 gap-3 text-slate-300">
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Title</span>
                    <span className="font-medium text-white">{title}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Type</span>
                    <span className="font-medium text-amber-400">{campaignType}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Listings Included</span>
                    <span className="font-medium text-white">{selectedListingIds.length} approved listing(s)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Duration & Start</span>
                    <span className="font-medium text-white">
                      {quote?.duration_days} Days (Starts {startDate || "Tomorrow"})
                    </span>
                  </div>
                </div>
              </div>

              {quote && (
                <div className="p-4 rounded-xl bg-amber-400/10 border border-amber-400/30 flex items-center justify-between">
                  <div>
                    <span className="text-xs font-semibold text-amber-200">Total Statutory Investment</span>
                    <p className="text-[10px] text-amber-400/80">Includes applicable {quote.tax_regime}</p>
                  </div>
                  <span className="text-xl font-black text-amber-400">
                    {currency} {(quote.total_amount_minor / 100).toFixed(2)}
                  </span>
                </div>
              )}

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-slate-400 text-[11px] space-y-2">
                <div className="flex items-center gap-2 text-white font-semibold">
                  <Info className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>Platform Advertising & Moderation Guidelines</span>
                </div>
                <ul className="list-disc list-inside space-y-1 text-slate-400">
                  <li>Campaigns are reviewed by platform staff prior to activation.</li>
                  <li>Payment is charged securely via Stripe (UK) or Razorpay (India) once approved.</li>
                  <li>Pro-rata whole-day refunds apply if you cancel before completion.</li>
                  <li>Listings must remain in APPROVED status to receive sponsored placement.</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/50 flex items-center justify-between">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((step - 1) as 1 | 2 | 3 | 4)}
              disabled={submitting}
              className="px-4 py-2 rounded-xl border border-slate-800 text-slate-300 hover:bg-slate-800 text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Back</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-semibold transition"
            >
              Cancel
            </button>
          )}

          {step < 4 ? (
            <button
              type="button"
              onClick={handleNext}
              className="px-5 py-2.5 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 text-xs font-bold flex items-center gap-1.5 transition shadow-lg shadow-amber-400/10"
            >
              <span>Continue</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleSubmit(false)}
                disabled={submitting}
                className="px-4 py-2.5 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-200 text-xs font-semibold transition disabled:opacity-50"
              >
                Save as Draft
              </button>
              <button
                type="button"
                onClick={() => handleSubmit(true)}
                disabled={submitting}
                className="px-5 py-2.5 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 text-xs font-bold flex items-center gap-1.5 transition shadow-lg shadow-amber-400/20 disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Submitting...</span>
                  </>
                ) : (
                  <>
                    <span>Submit for Approval</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
