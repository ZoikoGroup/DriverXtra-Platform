"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  ShoppingCart,
  X,
  Plus,
  Minus,
  Trash2,
  Store,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  RefreshCw,
  Wrench,
  PackageCheck,
  Car,
  MapPin,
  Phone,
  User as UserIcon,
  Check,
  Copy,
  Loader2,
  Receipt,
  Truck,
  Building,
  Package,
} from "lucide-react";
import { useCart, CartItem } from "@/context/CartContext";
import { api, ApiError, resolveMediaUrl, PlatformOrder } from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";

interface CartDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate?: (tab: string, itemData?: { type: string; id: string; raw?: unknown }) => void;
}

type CheckoutStep = "cart" | "shipping" | "review" | "confirmed";

interface ShippingFormData {
  shipping_name: string;
  shipping_phone: string;
  shipping_address_line1: string;
  shipping_address_line2: string;
  shipping_city: string;
  shipping_state: string;
  shipping_postal_code: string;
  shipping_country: string;
}

interface CalculatedItem {
  listing_id: string;
  title: string;
  brand: string;
  mpn?: string;
  hsn_code?: string;
  gst_rate: string;
  unit_price: string;
  quantity: number;
  taxable_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  tax_amount: string;
  total_amount: string;
}

interface AuthoritativeCalculation {
  subtotal_taxable_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  total_tax_amount: string;
  total_amount: string;
  currency: string;
  place_of_supply?: string;
  seller_state?: string;
  items: CalculatedItem[];
}

const INDIAN_STATES = [
  { code: "MH", name: "Maharashtra (MH)" },
  { code: "DL", name: "Delhi (DL)" },
  { code: "KA", name: "Karnataka (KA)" },
  { code: "TN", name: "Tamil Nadu (TN)" },
  { code: "TS", name: "Telangana (TS)" },
  { code: "GJ", name: "Gujarat (GJ)" },
  { code: "UP", name: "Uttar Pradesh (UP)" },
  { code: "HR", name: "Haryana (HR)" },
  { code: "WB", name: "West Bengal (WB)" },
  { code: "RJ", name: "Rajasthan (RJ)" },
  { code: "KL", name: "Kerala (KL)" },
  { code: "AP", name: "Andhra Pradesh (AP)" },
  { code: "MP", name: "Madhya Pradesh (MP)" },
  { code: "PB", name: "Punjab (PB)" },
  { code: "BR", name: "Bihar (BR)" },
  { code: "OR", name: "Odisha (OR)" },
  { code: "AS", name: "Assam (AS)" },
  { code: "CH", name: "Chandigarh (CH)" },
  { code: "GA", name: "Goa (GA)" },
  { code: "UK", name: "Uttarakhand (UK)" },
  { code: "JH", name: "Jharkhand (JH)" },
];

export default function CartDrawer({ isOpen, onClose, onNavigate }: CartDrawerProps) {
  const { user } = useAuth();
  const {
    items,
    totalUnits,
    distinctItemCount,
    displayedSubtotal,
    currency,
    groupedBySeller,
    updateQuantity,
    removeItem,
    clearCart,
    validateInventory,
    isValidating,
    lastValidationResult,
  } = useCart();

  // Multi-step checkout states
  const [step, setStep] = useState<CheckoutStep>("cart");
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [checkoutNotice, setCheckoutNotice] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [priceChangeAlert, setPriceChangeAlert] = useState<{
    reviewed: string;
    updated: string;
  } | null>(null);

  // Loading & submission locks
  const [isCalculating, setIsCalculating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState<string>("");
  const [copiedOrderId, setCopiedOrderId] = useState(false);

  // Authoritative calculation & order confirmation data
  const [calculation, setCalculation] = useState<AuthoritativeCalculation | null>(null);
  const [confirmedOrder, setConfirmedOrder] = useState<PlatformOrder | null>(null);

  // Shipping Form State
  const [shippingForm, setShippingForm] = useState<ShippingFormData>({
    shipping_name: "",
    shipping_phone: "",
    shipping_address_line1: "",
    shipping_address_line2: "",
    shipping_city: "",
    shipping_state: "MH",
    shipping_postal_code: "",
    shipping_country: "India",
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const drawerRef = useRef<HTMLDivElement>(null);

  // Auto-fill user details when available
  useEffect(() => {
    if (user) {
      setShippingForm((prev) => ({
        ...prev,
        shipping_name: prev.shipping_name || user.fullName || "",
      }));
    }
  }, [user]);

  // Reset checkout flow when drawer is opened/closed
  useEffect(() => {
    if (!isOpen) {
      // If order was confirmed, reset to cart step for next open
      if (step === "confirmed") {
        setStep("cart");
        setConfirmedOrder(null);
      }
      setCheckoutNotice(null);
      setCheckoutError(null);
      setPriceChangeAlert(null);
    }
  }, [isOpen, step]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  // Helpers
  const partItems = items.filter((i) => i.listing_type !== "vehicle");
  const hasVehicles = items.some((i) => i.listing_type === "vehicle");

  const generateNewIdempotencyKey = () => {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `dx-idem-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  };

  const handleBrowseParts = () => {
    onClose();
    if (onNavigate) {
      onNavigate("marketplace_browse");
    }
  };

  // Step 1 -> Step 2: Proceed from Cart to Shipping
  const handleProceedToShipping = async () => {
    setCheckoutNotice(null);
    setCheckoutError(null);
    setPriceChangeAlert(null);

    if (hasVehicles) {
      setCheckoutError(
        "Notice: Your cart contains a vehicle listing. Motor vehicles require legal documentation, physical inspection, and direct seller consultation. Please use the Contact Seller enquiry flow; online automated checkout is reserved exclusively for spare parts."
      );
      return;
    }

    if (partItems.length === 0) {
      setCheckoutError("Your cart contains no spare parts to checkout.");
      return;
    }

    if (!user) {
      setCheckoutError(
        "Please sign in to your DriverXtra account to place an order with verified statutory taxes and delivery details."
      );
      return;
    }

    // Verify stock
    const valResult = await validateInventory();
    if (!valResult.isValid) {
      return;
    }

    setStep("shipping");
  };

  // Step 2 -> Step 3: Validate Shipping Form & Calculate Authoritative Tax
  const handleProceedToReview = async () => {
    setCheckoutError(null);
    setPriceChangeAlert(null);

    // Validate fields
    const errors: Record<string, string> = {};
    if (!shippingForm.shipping_name.trim()) {
      errors.shipping_name = "Full name is required for delivery.";
    }
    const cleanPhone = shippingForm.shipping_phone.replace(/[^0-9+]/g, "");
    if (!shippingForm.shipping_phone.trim()) {
      errors.shipping_phone = "Contact phone number is required.";
    } else if (cleanPhone.length < 7) {
      errors.shipping_phone = "A valid phone number (at least 7 digits) is required.";
    }
    if (!shippingForm.shipping_address_line1.trim()) {
      errors.shipping_address_line1 = "Delivery street address is required.";
    }
    if (!shippingForm.shipping_city.trim()) {
      errors.shipping_city = "City is required.";
    }
    if (!shippingForm.shipping_state.trim()) {
      errors.shipping_state = "State / Place of supply is required.";
    }
    if (!shippingForm.shipping_postal_code.trim()) {
      errors.shipping_postal_code = "Postal / PIN code is required.";
    }

    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setCheckoutError("Please fill in all required shipping and contact details.");
      return;
    }

    setIsCalculating(true);
    try {
      const payload = {
        items: partItems.map((i) => ({
          listing_id: i.listing_id,
          quantity: i.quantity,
        })),
        place_of_supply: shippingForm.shipping_state,
        shipping_name: shippingForm.shipping_name.trim(),
        shipping_phone: shippingForm.shipping_phone.trim(),
        shipping_address_line1: shippingForm.shipping_address_line1.trim(),
        shipping_address_line2: shippingForm.shipping_address_line2.trim(),
        shipping_city: shippingForm.shipping_city.trim(),
        shipping_state: shippingForm.shipping_state.trim(),
        shipping_postal_code: shippingForm.shipping_postal_code.trim(),
        shipping_country: shippingForm.shipping_country.trim() || "India",
        currency: currency,
      };

      const res = await api.marketplace.calculateCheckout(payload);

      const itemsList: CalculatedItem[] = Array.isArray(res.items)
        ? (res.items as CalculatedItem[])
        : [];

      const calcData: AuthoritativeCalculation = {
        subtotal_taxable_amount: String(res.subtotal_taxable_amount || "0.00"),
        cgst_amount: String(res.cgst_amount || "0.00"),
        sgst_amount: String(res.sgst_amount || "0.00"),
        igst_amount: String(res.igst_amount || "0.00"),
        total_tax_amount: String(res.total_tax_amount || "0.00"),
        total_amount: String(res.total_amount || "0.00"),
        currency: String(res.currency || currency),
        place_of_supply: String(res.place_of_supply || shippingForm.shipping_state),
        seller_state: String(res.seller_state || ""),
        items: itemsList,
      };

      setCalculation(calcData);
      // Ensure idempotency key is initialized for this checkout attempt
      if (!idempotencyKey) {
        setIdempotencyKey(generateNewIdempotencyKey());
      }
      setStep("review");
    } catch (err: unknown) {
      let msg = "Failed to calculate taxes with backend.";
      if (err instanceof ApiError) {
        msg = err.message;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setCheckoutError(msg);
    } finally {
      setIsCalculating(false);
    }
  };

  // Step 3 -> Step 4: Final Submit Order
  const handleSubmitOrder = async () => {
    if (!calculation || isSubmitting) return;

    setIsSubmitting(true);
    setCheckoutError(null);

    const activeIdempotencyKey = idempotencyKey || generateNewIdempotencyKey();
    if (!idempotencyKey) {
      setIdempotencyKey(activeIdempotencyKey);
    }

    try {
      const payload = {
        items: partItems.map((i) => ({
          listing_id: i.listing_id,
          quantity: i.quantity,
        })),
        place_of_supply: shippingForm.shipping_state,
        shipping_name: shippingForm.shipping_name.trim(),
        shipping_phone: shippingForm.shipping_phone.trim(),
        shipping_address_line1: shippingForm.shipping_address_line1.trim(),
        shipping_address_line2: shippingForm.shipping_address_line2.trim(),
        shipping_city: shippingForm.shipping_city.trim(),
        shipping_state: shippingForm.shipping_state.trim(),
        shipping_postal_code: shippingForm.shipping_postal_code.trim(),
        shipping_country: shippingForm.shipping_country.trim() || "India",
        currency: calculation.currency,
        expected_total_amount: calculation.total_amount,
        idempotency_key: activeIdempotencyKey,
      };

      const res = await api.marketplace.checkout(payload);

      if (res.status === "success" && res.order) {
        // Authoritative success confirmed by backend!
        // Clear cart ONLY now!
        clearCart();
        setConfirmedOrder(res.order);
        setStep("confirmed");
      } else {
        throw new Error(res.message || "Failed to create order.");
      }
    } catch (err: unknown) {
      // PRICE CHANGED (HTTP 409)
      if (err instanceof ApiError && err.code === 409) {
        const details = err.details as Record<string, unknown> | undefined;
        const reviewedTotal = String(details?.reviewed_total_amount || calculation.total_amount);
        const updatedTotal = String(details?.updated_total_amount || "");

        if (updatedTotal) {
          setPriceChangeAlert({
            reviewed: reviewedTotal,
            updated: updatedTotal,
          });
          // Update calculation with newly authoritative values
          setCalculation((prev) =>
            prev
              ? {
                  ...prev,
                  total_amount: updatedTotal,
                  subtotal_taxable_amount: String(details?.subtotal_taxable_amount || prev.subtotal_taxable_amount),
                  total_tax_amount: String(details?.total_tax_amount || prev.total_tax_amount),
                }
              : null
          );
        } else {
          setPriceChangeAlert({
            reviewed: reviewedTotal,
            updated: "Updated Total",
          });
        }
        setCheckoutError(err.message);
        // Cart is NOT cleared!
        return;
      }

      // Other ApiError or Network failure
      let msg = "An error occurred during checkout submission.";
      if (err instanceof ApiError) {
        msg = err.message;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setCheckoutError(msg);
      // Cart is NOT cleared on failure or timeout!
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyOrderId = (idToCopy: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(idToCopy);
      setCopiedOrderId(true);
      setTimeout(() => setCopiedOrderId(false), 2000);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end animate-in fade-in duration-200"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Shopping Cart & Checkout"
    >
      <div
        ref={drawerRef}
        className="bg-white w-full max-w-xl h-full shadow-2xl flex flex-col border-l border-slate-200 animate-in slide-in-from-right duration-250 select-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ========================================================= */}
        {/* TOP BAR / STEP HEADER                                      */}
        {/* ========================================================= */}
        <div className="p-4 sm:p-5 border-b border-slate-200 flex items-center justify-between bg-slate-900 text-white shrink-0">
          <div className="flex items-center gap-3">
            {step === "cart" ? (
              <div className="w-9 h-9 rounded-xl bg-amber-400 text-slate-950 flex items-center justify-center font-black shadow-md">
                <ShoppingCart className="w-5 h-5" />
              </div>
            ) : step === "shipping" ? (
              <button
                type="button"
                onClick={() => setStep("cart")}
                className="w-9 h-9 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center justify-center transition-colors"
                title="Back to Cart"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
            ) : step === "review" ? (
              <button
                type="button"
                onClick={() => setStep("shipping")}
                className="w-9 h-9 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center justify-center transition-colors"
                title="Back to Shipping Details"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
            ) : (
              <div className="w-9 h-9 rounded-xl bg-emerald-500 text-white flex items-center justify-center font-black shadow-md">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            )}

            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-black tracking-tight">
                  {step === "cart" && "Shopping Cart"}
                  {step === "shipping" && "Checkout: Delivery Address"}
                  {step === "review" && "Checkout: Review & Confirm"}
                  {step === "confirmed" && "Order Placed Successfully"}
                </h3>
                {step === "cart" && totalUnits > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-400/30 text-[10px] font-black font-mono">
                    {totalUnits} {totalUnits === 1 ? "unit" : "units"}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400">
                {step === "cart" && "Phase 4 Marketplace Commerce · Spare Parts"}
                {step === "shipping" && "Step 1 of 2: Shipping & Contact Information"}
                {step === "review" && "Step 2 of 2: Authoritative Tax Breakdown & Confirmation"}
                {step === "confirmed" && "Order recorded with immutable backend ledger"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {step === "cart" && items.length > 0 && (
              <button
                type="button"
                onClick={() => setConfirmClearOpen(true)}
                className="text-[11px] font-bold text-slate-400 hover:text-rose-400 px-2 py-1 rounded-lg hover:bg-slate-800 transition-colors"
                title="Clear all cart items"
              >
                Clear Cart
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Step Progress Bar (when checking out) */}
        {step !== "cart" && (
          <div className="bg-slate-800 px-5 py-2.5 flex items-center justify-between text-[11px] font-bold text-slate-400 border-b border-slate-700">
            <div className={`flex items-center gap-1.5 ${step === "shipping" ? "text-amber-400" : "text-emerald-400"}`}>
              <span className="w-5 h-5 rounded-full bg-slate-700 flex items-center justify-center text-[10px]">1</span>
              <span>Delivery Details</span>
            </div>
            <div className="w-8 h-px bg-slate-700" />
            <div className={`flex items-center gap-1.5 ${step === "review" ? "text-amber-400" : step === "confirmed" ? "text-emerald-400" : "text-slate-500"}`}>
              <span className="w-5 h-5 rounded-full bg-slate-700 flex items-center justify-center text-[10px]">2</span>
              <span>Review & Taxes</span>
            </div>
            <div className="w-8 h-px bg-slate-700" />
            <div className={`flex items-center gap-1.5 ${step === "confirmed" ? "text-emerald-400" : "text-slate-500"}`}>
              <span className="w-5 h-5 rounded-full bg-slate-700 flex items-center justify-center text-[10px]">3</span>
              <span>Confirmed</span>
            </div>
          </div>
        )}

        {/* Clear Confirmation Prompt */}
        {confirmClearOpen && (
          <div className="p-3 bg-rose-50 border-b border-rose-200 text-rose-900 text-xs flex items-center justify-between gap-3 animate-in fade-in duration-150">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>Are you sure you want to remove all items from your cart?</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => {
                  clearCart();
                  setConfirmClearOpen(false);
                }}
                className="px-2.5 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-bold text-[11px]"
              >
                Yes, Clear
              </button>
              <button
                type="button"
                onClick={() => setConfirmClearOpen(false)}
                className="px-2.5 py-1 bg-white hover:bg-slate-100 text-slate-700 rounded-lg font-bold text-[11px] border border-slate-200"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Error Alert Banner */}
        {checkoutError && (
          <div className="p-3 bg-rose-50 border-b border-rose-200 text-rose-950 text-xs flex items-start gap-2 animate-in fade-in duration-150">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold text-rose-900">{checkoutError}</p>
            </div>
            <button
              type="button"
              onClick={() => setCheckoutError(null)}
              className="text-rose-700 hover:text-rose-900 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Price Change Explicit Notice Banner */}
        {priceChangeAlert && (
          <div className="p-3 bg-amber-500/10 border-b border-amber-400 text-amber-950 text-xs flex items-start gap-2 animate-in fade-in duration-150">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="flex-1 space-y-1">
              <p className="font-black text-amber-900">
                Action Required: Order Total Updated by Seller/Tax Rules
              </p>
              <p className="text-[11px] text-amber-900">
                The authoritative server total has changed from{" "}
                <span className="font-mono font-bold line-through">{priceChangeAlert.reviewed}</span> to{" "}
                <span className="font-mono font-black text-slate-950 bg-amber-200 px-1 py-0.5 rounded">
                  {priceChangeAlert.updated}
                </span>{" "}
                due to live listing price updates or place-of-supply statutory taxes. Please review the updated total and explicitly confirm before submission.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setPriceChangeAlert(null)}
              className="text-amber-800 hover:text-amber-950 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Notice Banner */}
        {checkoutNotice && (
          <div className="p-3 bg-emerald-50 border-b border-emerald-200 text-emerald-950 text-xs flex items-start gap-2 animate-in fade-in duration-150">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold">{checkoutNotice}</p>
            </div>
            <button
              type="button"
              onClick={() => setCheckoutNotice(null)}
              className="text-emerald-700 hover:text-emerald-900 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* ========================================================= */}
        {/* BODY CONTENT: STEP BY STEP                                */}
        {/* ========================================================= */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5 bg-slate-50">
          {/* STEP 1: CART VIEW */}
          {step === "cart" && (
            <>
              {items.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4">
                  <div className="w-20 h-20 rounded-3xl bg-slate-200/80 flex items-center justify-center text-slate-400">
                    <ShoppingCart className="w-10 h-10" />
                  </div>
                  <div className="space-y-1 max-w-xs">
                    <h4 className="text-base font-black text-slate-900">Your basket is empty</h4>
                    <p className="text-xs text-slate-500">
                      You haven&apos;t added any verified spare parts to your shopping cart yet.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleBrowseParts}
                    className="mt-2 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow-md flex items-center gap-2"
                  >
                    <Wrench className="w-4 h-4 text-amber-400" />
                    <span>Browse Spare Parts Marketplace</span>
                  </button>
                </div>
              ) : (
                <>
                  {/* Vehicle Advisory if vehicle is in cart */}
                  {hasVehicles && (
                    <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-amber-950 text-xs flex items-start gap-2">
                      <Car className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                      <div className="space-y-0.5">
                        <span className="font-bold text-amber-900 block">Vehicles are enquiry-based</span>
                        <p className="text-[11px] text-amber-800">
                          Automated checkout is supported strictly for spare parts. Motor vehicles require legal documentation, physical inspection, and title transfer. Please contact the seller via the Contact Seller button on the listing.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Grouped by Seller / Dealership */}
                  {groupedBySeller.map((group) => (
                    <div
                      key={group.sellerKey}
                      className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs space-y-3 p-4"
                    >
                      {/* Seller Header */}
                      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="w-6 h-6 rounded-lg bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600 shrink-0">
                            <Store className="w-3.5 h-3.5" />
                          </div>
                          <div className="min-w-0">
                            <span className="text-xs font-black text-slate-900 truncate block">
                              {group.sellerName}
                            </span>
                            {group.organisationName && (
                              <span className="text-[10px] text-slate-500 block truncate">
                                Dealership: {group.organisationName}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <span className="text-[10px] uppercase font-bold text-slate-400 block">
                            Subtotal
                          </span>
                          <span className="text-xs font-black text-slate-900 font-mono">
                            {currency} {group.subtotal.toFixed(2)}
                          </span>
                        </div>
                      </div>

                      {/* Items for this seller */}
                      <div className="space-y-3">
                        {group.items.map((item) => (
                          <CartItemRow
                            key={item.listing_id}
                            item={item}
                            onUpdateQuantity={(qty) => updateQuantity(item.listing_id, qty)}
                            onRemove={() => removeItem(item.listing_id)}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}

          {/* STEP 2: SHIPPING FORM */}
          {step === "shipping" && (
            <div className="space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-5 shadow-xs space-y-4">
                <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                  <div className="w-7 h-7 rounded-lg bg-amber-100 text-amber-800 flex items-center justify-center font-bold">
                    <Truck className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-black text-slate-900 uppercase tracking-wide">
                      Buyer & Delivery Details
                    </h4>
                    <p className="text-[10px] text-slate-500">
                      Statutory GST and shipping dispatch depend on your destination state
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-xs">
                  {/* Recipient Full Name */}
                  <div className="sm:col-span-2 space-y-1">
                    <label className="font-bold text-slate-700 flex items-center gap-1">
                      <UserIcon className="w-3 h-3 text-slate-400" />
                      <span>Full Name / Company Name *</span>
                    </label>
                    <input
                      type="text"
                      id="shipping-name-input"
                      value={shippingForm.shipping_name}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_name: e.target.value }))
                      }
                      placeholder="e.g. Rahul Sharma"
                      className={`w-full px-3 py-2 bg-slate-50 rounded-xl border ${
                        fieldErrors.shipping_name ? "border-rose-400 bg-rose-50/30" : "border-slate-200"
                      } focus:outline-hidden focus:border-amber-500 text-slate-900`}
                    />
                    {fieldErrors.shipping_name && (
                      <p className="text-[10px] text-rose-600 font-medium">{fieldErrors.shipping_name}</p>
                    )}
                  </div>

                  {/* Phone Number */}
                  <div className="sm:col-span-2 space-y-1">
                    <label className="font-bold text-slate-700 flex items-center gap-1">
                      <Phone className="w-3 h-3 text-slate-400" />
                      <span>Contact Phone Number *</span>
                    </label>
                    <input
                      type="tel"
                      id="shipping-phone-input"
                      value={shippingForm.shipping_phone}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_phone: e.target.value }))
                      }
                      placeholder="e.g. +91 98765 43210"
                      className={`w-full px-3 py-2 bg-slate-50 rounded-xl border ${
                        fieldErrors.shipping_phone ? "border-rose-400 bg-rose-50/30" : "border-slate-200"
                      } focus:outline-hidden focus:border-amber-500 text-slate-900`}
                    />
                    {fieldErrors.shipping_phone && (
                      <p className="text-[10px] text-rose-600 font-medium">{fieldErrors.shipping_phone}</p>
                    )}
                  </div>

                  {/* Street Address Line 1 */}
                  <div className="sm:col-span-2 space-y-1">
                    <label className="font-bold text-slate-700 flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-slate-400" />
                      <span>Address Line 1 (Street, Building, Flat) *</span>
                    </label>
                    <input
                      type="text"
                      id="shipping-address1-input"
                      value={shippingForm.shipping_address_line1}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_address_line1: e.target.value }))
                      }
                      placeholder="e.g. 104, Auto Hub Industrial Area, Andheri East"
                      className={`w-full px-3 py-2 bg-slate-50 rounded-xl border ${
                        fieldErrors.shipping_address_line1 ? "border-rose-400 bg-rose-50/30" : "border-slate-200"
                      } focus:outline-hidden focus:border-amber-500 text-slate-900`}
                    />
                    {fieldErrors.shipping_address_line1 && (
                      <p className="text-[10px] text-rose-600 font-medium">{fieldErrors.shipping_address_line1}</p>
                    )}
                  </div>

                  {/* Street Address Line 2 */}
                  <div className="sm:col-span-2 space-y-1">
                    <label className="font-medium text-slate-600">Address Line 2 (Optional landmark, suite)</label>
                    <input
                      type="text"
                      id="shipping-address2-input"
                      value={shippingForm.shipping_address_line2}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_address_line2: e.target.value }))
                      }
                      placeholder="Near Metro Station Pillar 12"
                      className="w-full px-3 py-2 bg-slate-50 rounded-xl border border-slate-200 focus:outline-hidden focus:border-amber-500 text-slate-900"
                    />
                  </div>

                  {/* City */}
                  <div className="space-y-1">
                    <label className="font-bold text-slate-700">City / District *</label>
                    <input
                      type="text"
                      id="shipping-city-input"
                      value={shippingForm.shipping_city}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_city: e.target.value }))
                      }
                      placeholder="e.g. Mumbai"
                      className={`w-full px-3 py-2 bg-slate-50 rounded-xl border ${
                        fieldErrors.shipping_city ? "border-rose-400 bg-rose-50/30" : "border-slate-200"
                      } focus:outline-hidden focus:border-amber-500 text-slate-900`}
                    />
                    {fieldErrors.shipping_city && (
                      <p className="text-[10px] text-rose-600 font-medium">{fieldErrors.shipping_city}</p>
                    )}
                  </div>

                  {/* Postal Code */}
                  <div className="space-y-1">
                    <label className="font-bold text-slate-700">Postal / PIN Code *</label>
                    <input
                      type="text"
                      id="shipping-postal-input"
                      value={shippingForm.shipping_postal_code}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_postal_code: e.target.value }))
                      }
                      placeholder="e.g. 400069"
                      className={`w-full px-3 py-2 bg-slate-50 rounded-xl border ${
                        fieldErrors.shipping_postal_code ? "border-rose-400 bg-rose-50/30" : "border-slate-200"
                      } focus:outline-hidden focus:border-amber-500 text-slate-900`}
                    />
                    {fieldErrors.shipping_postal_code && (
                      <p className="text-[10px] text-rose-600 font-medium">{fieldErrors.shipping_postal_code}</p>
                    )}
                  </div>

                  {/* State / Place of Supply */}
                  <div className="space-y-1">
                    <label className="font-bold text-slate-700 flex items-center justify-between">
                      <span>State (Place of Supply) *</span>
                      <span className="text-[10px] text-amber-600 font-semibold">Statutory GST</span>
                    </label>
                    <select
                      id="shipping-state-select"
                      value={shippingForm.shipping_state}
                      onChange={(e) =>
                        setShippingForm((p) => ({ ...p, shipping_state: e.target.value }))
                      }
                      className="w-full px-3 py-2 bg-slate-50 rounded-xl border border-slate-200 focus:outline-hidden focus:border-amber-500 text-slate-900 font-medium"
                    >
                      {INDIAN_STATES.map((st) => (
                        <option key={st.code} value={st.code}>
                          {st.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Country */}
                  <div className="space-y-1">
                    <label className="font-bold text-slate-700">Country</label>
                    <input
                      type="text"
                      disabled
                      value={shippingForm.shipping_country}
                      className="w-full px-3 py-2 bg-slate-100 rounded-xl border border-slate-200 text-slate-600 font-medium cursor-not-allowed"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: REVIEW & AUTHORITATIVE BREAKDOWN VIEW */}
          {step === "review" && calculation && (
            <div className="space-y-4">
              {/* Destination Address Pill */}
              <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center shrink-0">
                    <MapPin className="w-4 h-4" />
                  </div>
                  <div className="text-xs space-y-0.5">
                    <span className="font-black text-slate-900 block">{shippingForm.shipping_name}</span>
                    <p className="text-slate-600 text-[11px]">
                      {shippingForm.shipping_address_line1}
                      {shippingForm.shipping_address_line2 ? `, ${shippingForm.shipping_address_line2}` : ""},{" "}
                      {shippingForm.shipping_city}, {shippingForm.shipping_state} -{" "}
                      {shippingForm.shipping_postal_code}
                    </p>
                    <p className="text-slate-500 text-[10px] font-mono">Contact: {shippingForm.shipping_phone}</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setStep("shipping")}
                  className="text-xs font-bold text-amber-600 hover:text-amber-700 underline shrink-0"
                >
                  Edit
                </button>
              </div>

              {/* Items in Order */}
              <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <h4 className="text-xs font-black text-slate-900 uppercase tracking-wide flex items-center gap-1.5">
                    <PackageCheck className="w-4 h-4 text-amber-600" />
                    <span>Items to Order ({partItems.length})</span>
                  </h4>
                  <span className="text-[10px] text-slate-500 font-mono">
                    Place of Supply: {calculation.place_of_supply}
                  </span>
                </div>

                <div className="space-y-2.5">
                  {calculation.items.map((ci) => (
                    <div
                      key={ci.listing_id}
                      className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex items-start justify-between gap-3 text-xs"
                    >
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[9px] uppercase font-bold bg-amber-100 text-amber-800 px-1.5 py-0.2 rounded">
                            {ci.brand}
                          </span>
                          {ci.hsn_code && (
                            <span className="text-[9px] text-slate-500 font-mono">
                              HSN: {ci.hsn_code}
                            </span>
                          )}
                          <span className="text-[9px] text-slate-600 font-semibold bg-slate-200 px-1 py-0.2 rounded">
                            GST {ci.gst_rate}%
                          </span>
                        </div>
                        <h5 className="font-bold text-slate-900 truncate" title={ci.title}>
                          {ci.title}
                        </h5>
                        <p className="text-[11px] text-slate-500">
                          {ci.quantity} × {calculation.currency} {Number(ci.unit_price).toFixed(2)}
                        </p>
                      </div>

                      <div className="text-right shrink-0">
                        <span className="font-mono font-bold text-slate-900 block">
                          {calculation.currency} {Number(ci.total_amount).toFixed(2)}
                        </span>
                        <span className="text-[9px] text-slate-400 block">
                          Tax: {calculation.currency} {Number(ci.tax_amount).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Authoritative Tax Breakdown Card */}
              <div className="bg-slate-900 text-white rounded-2xl border border-slate-800 p-4 space-y-2.5 shadow-md">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <span className="text-xs font-black tracking-wide text-amber-400 flex items-center gap-1.5">
                    <Receipt className="w-4 h-4" />
                    <span>Statutory Tax & Order Summary</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-400/30 font-bold">
                    ✓ Server Verified
                  </span>
                </div>

                <div className="space-y-1.5 text-xs text-slate-300">
                  <div className="flex justify-between">
                    <span>Taxable Value (Before GST):</span>
                    <span className="font-mono text-white">
                      {calculation.currency} {Number(calculation.subtotal_taxable_amount).toFixed(2)}
                    </span>
                  </div>

                  {Number(calculation.cgst_amount) > 0 && (
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Central GST (CGST):</span>
                      <span className="font-mono">
                        + {calculation.currency} {Number(calculation.cgst_amount).toFixed(2)}
                      </span>
                    </div>
                  )}

                  {Number(calculation.sgst_amount) > 0 && (
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>State GST (SGST):</span>
                      <span className="font-mono">
                        + {calculation.currency} {Number(calculation.sgst_amount).toFixed(2)}
                      </span>
                    </div>
                  )}

                  {Number(calculation.igst_amount) > 0 && (
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Integrated GST (IGST - Inter-State):</span>
                      <span className="font-mono">
                        + {calculation.currency} {Number(calculation.igst_amount).toFixed(2)}
                      </span>
                    </div>
                  )}

                  <div className="flex justify-between text-amber-400 font-semibold pt-1 border-t border-slate-800">
                    <span>Total Statutory GST:</span>
                    <span className="font-mono">
                      + {calculation.currency} {Number(calculation.total_tax_amount).toFixed(2)}
                    </span>
                  </div>
                </div>

                <div className="flex justify-between items-baseline pt-2 border-t border-slate-800">
                  <div>
                    <span className="text-sm font-black text-white block">Final Order Total</span>
                    <span className="text-[10px] text-slate-400">Inclusive of all statutory taxes</span>
                  </div>
                  <span className="text-xl font-black text-amber-400 font-mono">
                    {calculation.currency} {Number(calculation.total_amount).toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: ORDER CONFIRMED VIEW */}
          {step === "confirmed" && confirmedOrder && (
            <div className="space-y-5 text-center animate-in fade-in duration-300">
              <div className="py-6 flex flex-col items-center justify-center space-y-3">
                <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shadow-inner">
                  <CheckCircle2 className="w-10 h-10" />
                </div>
                <div className="space-y-1 max-w-sm">
                  <h4 className="text-xl font-black text-slate-900 tracking-tight">
                    Order Received Successfully!
                  </h4>
                  <p className="text-xs text-slate-500">
                    Your order has been recorded with the DriverXtra backend. An immutable audit record has been generated.
                  </p>
                </div>
              </div>

              {/* Order Identifier & Status */}
              <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs text-left space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <span className="text-[10px] uppercase font-bold text-slate-400">Order Number</span>
                  <span className="text-[10px] font-black uppercase px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300">
                    {confirmedOrder.status}
                  </span>
                </div>

                <div className="flex items-center justify-between bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                  <span className="font-mono font-black text-sm text-slate-900 tracking-wide">
                    {confirmedOrder.order_number}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCopyOrderId(confirmedOrder.order_number)}
                    className="p-1.5 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-200/70 transition-colors flex items-center gap-1 text-[11px] font-semibold"
                    title="Copy order number"
                  >
                    {copiedOrderId ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                        <span className="text-emerald-700">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Delivery details recap */}
                <div className="text-xs text-slate-600 space-y-1 pt-1">
                  <p className="font-bold text-slate-900">
                    Deliver to: {confirmedOrder.shipping_name} ({confirmedOrder.shipping_phone})
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {confirmedOrder.shipping_address_line1}, {confirmedOrder.shipping_city},{" "}
                    {confirmedOrder.shipping_state} - {confirmedOrder.shipping_postal_code},{" "}
                    {confirmedOrder.shipping_country}
                  </p>
                </div>

                {/* Totals Breakdown */}
                <div className="pt-2 border-t border-slate-100 flex justify-between items-baseline">
                  <span className="text-xs font-bold text-slate-500">Total Charged:</span>
                  <span className="text-base font-black text-slate-950 font-mono">
                    {confirmedOrder.currency} {Number(confirmedOrder.total_amount).toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Status Note */}
              <div className="p-3 bg-slate-100 rounded-xl text-[11px] text-slate-600 text-left border border-slate-200">
                <span className="font-bold text-slate-800 block">Payment & Fulfillment Status</span>
                Order is registered with initial status <strong className="font-mono text-slate-900">PENDING_CONFIRMATION</strong>. As payment gateway integration is slated for Phase 5, payment has not been marked as paid.
              </div>

              {/* Actions */}
              <div className="pt-2 space-y-2">
                <button
                  type="button"
                  id="view-my-orders-btn"
                  onClick={() => {
                    const orderId = confirmedOrder.id;
                    onClose();
                    setStep("cart");
                    setConfirmedOrder(null);
                    if (onNavigate) {
                      onNavigate("my_orders", { type: "order", id: orderId });
                    }
                  }}
                  className="w-full py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2"
                >
                  <Package className="w-4 h-4" />
                  <span>View in My Orders</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    setStep("cart");
                    setConfirmedOrder(null);
                    if (onNavigate) {
                      onNavigate("marketplace_browse");
                    }
                  }}
                  className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold text-xs rounded-xl transition-all flex items-center justify-center gap-2"
                >
                  <Wrench className="w-4 h-4 text-slate-600" />
                  <span>Continue Shopping on Marketplace</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ========================================================= */}
        {/* FOOTER ACTIONS                                            */}
        {/* ========================================================= */}
        {step !== "confirmed" && items.length > 0 && (
          <div className="p-4 sm:p-5 border-t border-slate-200 bg-white space-y-3.5 shrink-0 shadow-lg">
            {/* STEP 1: CART ACTIONS */}
            {step === "cart" && (
              <>
                <div className="flex items-baseline justify-between">
                  <div>
                    <span className="text-xs text-slate-500 font-medium block">Cart Subtotal</span>
                    <span className="text-[10px] text-slate-400">Exclusive of statutory GST (calculated at next step)</span>
                  </div>
                  <span className="text-xl font-black text-slate-950 font-mono">
                    {currency} {displayedSubtotal.toFixed(2)}
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={validateInventory}
                    disabled={isValidating}
                    className="px-3.5 py-3 rounded-xl border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                    title="Verify stock availability and statutory tax with backend"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isValidating ? "animate-spin text-amber-500" : ""}`} />
                    <span className="hidden sm:inline">Verify Stock</span>
                  </button>

                  <button
                    type="button"
                    id="cart-proceed-checkout-btn"
                    onClick={handleProceedToShipping}
                    disabled={isValidating || partItems.length === 0}
                    className="flex-1 py-3 px-4 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span>Proceed to Delivery & Taxes</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              </>
            )}

            {/* STEP 2: SHIPPING ACTIONS */}
            {step === "shipping" && (
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setStep("cart")}
                  className="px-4 py-3 rounded-xl border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-bold transition-colors"
                >
                  Back to Cart
                </button>
                <button
                  type="button"
                  id="shipping-proceed-review-btn"
                  onClick={handleProceedToReview}
                  disabled={isCalculating}
                  className="flex-1 py-3 px-4 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isCalculating ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Computing Taxes...</span>
                    </>
                  ) : (
                    <>
                      <span>Review Taxes & Order Total</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            )}

            {/* STEP 3: REVIEW ACTIONS */}
            {step === "review" && calculation && (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setStep("shipping")}
                    disabled={isSubmitting}
                    className="px-4 py-3 rounded-xl border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-bold transition-colors disabled:opacity-50"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    id="submit-order-checkout-btn"
                    onClick={handleSubmitOrder}
                    disabled={isSubmitting}
                    className="flex-1 py-3 px-4 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Creating Order Safely...</span>
                      </>
                    ) : priceChangeAlert ? (
                      <>
                        <Check className="w-4 h-4" />
                        <span>Confirm & Submit Order ({calculation.currency} {Number(calculation.total_amount).toFixed(2)})</span>
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-4 h-4 text-slate-950" />
                        <span>Submit Order ({calculation.currency} {Number(calculation.total_amount).toFixed(2)})</span>
                      </>
                    )}
                  </button>
                </div>
                <p className="text-[10px] text-slate-400 text-center">
                  Protected against accidental repeated submissions · Stock locked during checkout
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CartItemRow({
  item,
  onUpdateQuantity,
  onRemove,
}: {
  item: CartItem;
  onUpdateQuantity: (qty: number) => void;
  onRemove: () => void;
}) {
  const isVehicle = item.listing_type === "vehicle";
  const lineTotal = item.price * item.quantity;
  const isAtMaxStock = item.quantity >= item.stock_quantity;
  const isExceedingStock = item.quantity > item.stock_quantity;

  return (
    <div className="p-3 bg-slate-50/70 rounded-xl border border-slate-100 flex gap-3 items-start relative group">
      {/* Thumbnail */}
      <div className="w-16 h-16 rounded-lg bg-slate-900 border border-slate-200 overflow-hidden flex items-center justify-center shrink-0">
        {item.image_url ? (
          <img
            src={resolveMediaUrl(item.image_url)}
            alt={item.title}
            className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = "none";
              const fb = e.currentTarget.parentElement?.querySelector(".cart-img-fb");
              if (fb) (fb as HTMLElement).style.display = "flex";
            }}
          />
        ) : null}
        <div
          className={`cart-img-fb w-full h-full flex items-center justify-center text-slate-600 ${
            item.image_url ? "hidden" : "flex"
          }`}
        >
          {isVehicle ? <Car className="w-6 h-6 text-amber-400" /> : <Wrench className="w-6 h-6" />}
        </div>
      </div>

      {/* Details */}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 py-0.2 rounded uppercase">
                {item.brand}
              </span>
              {isVehicle ? (
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-1.5 py-0.2 rounded flex items-center gap-0.5">
                  <Car className="w-2.5 h-2.5" />
                  Vehicle Asset
                </span>
              ) : item.mpn ? (
                <span className="text-[10px] text-slate-500 font-mono font-medium">
                  MPN: {item.mpn}
                </span>
              ) : null}
              <span className="text-[9px] text-slate-600 bg-slate-200 px-1 py-0.2 rounded font-semibold">
                {item.condition}
              </span>
            </div>
            <h4 className="text-xs font-bold text-slate-900 truncate mt-0.5" title={item.title}>
              {item.title}
            </h4>
          </div>

          {/* Remove Button */}
          <button
            type="button"
            onClick={onRemove}
            className="text-slate-400 hover:text-rose-600 p-1 rounded-lg hover:bg-slate-200/60 transition-colors shrink-0"
            title="Remove item from cart"
            aria-label={`Remove ${item.title}`}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Pricing & Stock Warning */}
        <div className="flex items-baseline justify-between pt-1">
          <div className="text-xs">
            <span className="font-mono font-black text-slate-900">
              {item.currency} {item.price.toFixed(2)}
            </span>
            <span className="text-[10px] text-slate-400 ml-1">
              {isVehicle ? "/ vehicle" : "/ unit"}
            </span>
          </div>

          <div className="text-right">
            <span className="text-[10px] text-slate-400 mr-1">Line total:</span>
            <span className="text-xs font-black text-amber-600 font-mono">
              {item.currency} {lineTotal.toFixed(2)}
            </span>
          </div>
        </div>

        {/* Stock Status Badge */}
        {isVehicle ? (
          <div className="text-[10px] font-bold text-amber-700 flex items-center gap-1 pt-0.5">
            <AlertCircle className="w-3 h-3 shrink-0" />
            <span>Enquiry Only · Motor vehicle asset</span>
          </div>
        ) : isExceedingStock ? (
          <div className="text-[10px] font-bold text-rose-600 flex items-center gap-1 pt-0.5">
            <AlertTriangle className="w-3 h-3 shrink-0" />
            <span>Quantity exceeds available stock ({item.stock_quantity})</span>
          </div>
        ) : isAtMaxStock ? (
          <div className="text-[10px] font-bold text-amber-600 flex items-center gap-1 pt-0.5">
            <PackageCheck className="w-3 h-3 shrink-0" />
            <span>Maximum stock reached ({item.stock_quantity} available)</span>
          </div>
        ) : null}

        {/* Quantity Controls */}
        <div className="pt-2 flex items-center justify-between">
          {isVehicle ? (
            <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg px-2 py-0.5 shadow-2xs text-[11px] font-bold text-slate-700">
              <Car className="w-3 h-3 text-amber-500 mr-1" />
              <span>Qty: 1 (Asset)</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-0.5 shadow-2xs">
              <button
                type="button"
                onClick={() => onUpdateQuantity(item.quantity - 1)}
                className="w-6 h-6 rounded flex items-center justify-center text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
                aria-label="Decrease quantity"
                title="Decrease quantity"
              >
                <Minus className="w-3 h-3" />
              </button>

              <span className="w-8 text-center text-xs font-black font-mono text-slate-900">
                {item.quantity}
              </span>

              <button
                type="button"
                onClick={() => onUpdateQuantity(item.quantity + 1)}
                disabled={isAtMaxStock}
                className="w-6 h-6 rounded flex items-center justify-center text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                aria-label="Increase quantity"
                title={isAtMaxStock ? "Maximum available stock reached" : "Increase quantity"}
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          )}

          <span className="text-[10px] text-slate-400">
            {isVehicle ? (
              <span>Asset: <strong className="text-slate-700">1 Unit</strong></span>
            ) : (
              <span>Stock: <strong className="text-slate-700">{item.stock_quantity}</strong></span>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
