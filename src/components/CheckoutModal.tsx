"use client";

import React, { useState } from "react";
import {
  Lock,
  ShieldCheck,
  CheckCircle2,
  QrCode,
  CreditCard,
  Building,
  ArrowRight,
  AlertCircle
} from "lucide-react";

interface CheckoutModalProps {
  item: any;
  type: "vehicle" | "part" | "service";
  onClose: () => void;
}

export default function CheckoutModal({ item, type, onClose }: CheckoutModalProps) {
  const [step, setStep] = useState<"review" | "processing" | "confirmed">("review");
  const [paymentMethod, setPaymentMethod] = useState<"card" | "wire">("card");

  const depositAmount = type === "vehicle" ? 500 : item.price;
  const isVehicle = type === "vehicle";

  const handlePay = () => {
    setStep("processing");
    setTimeout(() => {
      setStep("confirmed");
    }, 1600);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-3xl max-w-lg w-full p-6 sm:p-8 shadow-2xl border border-slate-200 my-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-amber-400 flex items-center justify-center text-slate-950 font-bold">
              <Lock className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-black text-slate-950">
                {isVehicle ? "Protected Escrow Reservation" : "Guaranteed Commerce Checkout"}
              </h3>
              <p className="text-[11px] text-slate-500">
                Commerce Saga (Doc 09) & Double-Entry Ledger (Doc 10)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 font-bold"
          >
            ✕
          </button>
        </div>

        {/* Step 1: Review & Pay */}
        {step === "review" && (
          <div className="mt-5 space-y-5">
            {/* Item summary */}
            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 flex gap-4 items-center">
              {item.image && (
                <img
                  src={item.image}
                  alt={item.title || item.name}
                  className="w-16 h-16 rounded-xl object-cover border border-slate-200"
                />
              )}
              <div className="flex-1 min-w-0">
                <span className="text-[10px] font-black uppercase text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                  {type.toUpperCase()} ITEM
                </span>
                <h4 className="text-sm font-bold text-slate-950 truncate mt-0.5">
                  {item.title || item.name}
                </h4>
                <div className="text-xs text-slate-500">
                  {isVehicle ? `Full Price: £${item.price.toLocaleString()} • Deposit Required` : `Qty: 1 • Guaranteed Fit`}
                </div>
              </div>
            </div>

            {/* Financial Ledger Breakdown */}
            <div className="space-y-2 text-xs border-y border-slate-100 py-3">
              <div className="flex justify-between text-slate-600">
                <span>{isVehicle ? "Refundable Escrow Reservation Deposit" : "Item Subtotal"}</span>
                <span className="font-bold text-slate-900">£{depositAmount.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-slate-600">
                <span>Dual-Custody Escrow Holding Fee (Doc 10)</span>
                <span className="font-bold text-emerald-600">FREE (£0.00)</span>
              </div>
              <div className="flex justify-between text-slate-600">
                <span>Jurisdiction Pack Tax Evaluation (UK VAT 20%)</span>
                <span className="font-bold text-slate-900">Included</span>
              </div>
              <div className="flex justify-between text-sm font-black text-slate-950 pt-2 border-t border-slate-100">
                <span>Total Authorization Today:</span>
                <span className="text-amber-600">£{depositAmount.toLocaleString()}</span>
              </div>
            </div>

            {/* Escrow safety alert */}
            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 flex items-start gap-2 text-xs text-amber-900">
              <ShieldCheck className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <strong className="font-bold">Funds Protection Guarantee:</strong> Money is held in regulated bank escrow. The seller cannot claim these funds until you inspect the vehicle or receive the physical part.
              </div>
            </div>

            {/* Payment Method Selector */}
            <div>
              <label className="block text-xs font-bold uppercase text-slate-500 mb-2">
                Select Regulated Payment Gateway
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setPaymentMethod("card")}
                  className={`p-3 rounded-xl border text-xs font-bold flex items-center justify-center gap-2 transition-all ${
                    paymentMethod === "card"
                      ? "border-slate-950 bg-slate-950 text-white shadow"
                      : "border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <CreditCard className="w-4 h-4 text-amber-400" />
                  <span>Card / Apple Pay</span>
                </button>

                <button
                  type="button"
                  onClick={() => setPaymentMethod("wire")}
                  className={`p-3 rounded-xl border text-xs font-bold flex items-center justify-center gap-2 transition-all ${
                    paymentMethod === "wire"
                      ? "border-slate-950 bg-slate-950 text-white shadow"
                      : "border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <Building className="w-4 h-4 text-amber-400" />
                  <span>Direct Bank Wire</span>
                </button>
              </div>
            </div>

            {/* Submit CTA */}
            <button
              onClick={handlePay}
              className="w-full h-12 rounded-xl bg-amber-400 hover:bg-amber-500 text-slate-950 font-black text-sm flex items-center justify-center gap-2 shadow-md transition-all hover:shadow-lg"
            >
              <Lock className="w-4 h-4" />
              <span>Authorize £{depositAmount.toLocaleString()} in Protected Escrow</span>
            </button>
          </div>
        )}

        {/* Step 2: Processing state machine */}
        {step === "processing" && (
          <div className="py-12 text-center space-y-4">
            <div className="w-16 h-16 border-4 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
            <h4 className="text-lg font-black text-slate-950">Orchestrating Transaction Saga...</h4>
            <div className="text-xs text-slate-500 max-w-xs mx-auto space-y-1">
              <p>✓ Revalidating PostgreSQL inventory position</p>
              <p>✓ Invoking PaymentIntent API via PSP Adapter</p>
              <p>✓ Creating Double-Entry Ledger Hold Journal</p>
            </div>
          </div>
        )}

        {/* Step 3: Confirmed with Handover QR Token */}
        {step === "confirmed" && (
          <div className="mt-5 text-center space-y-4">
            <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
            <div>
              <h4 className="text-xl font-black text-slate-950">
                {isVehicle ? "Vehicle Reserved & Escrow Secured!" : "Order Placed Successfully!"}
              </h4>
              <p className="text-xs text-slate-500 mt-1">
                Order Ref: <strong className="font-mono text-slate-900">DX-ORD-2026-98421</strong>
              </p>
            </div>

            {/* Handover QR token (Doc 09) */}
            <div className="p-5 bg-slate-950 text-white rounded-2xl border border-slate-800 flex flex-col items-center">
              <div className="w-32 h-32 bg-white rounded-xl p-2 flex items-center justify-center shadow-inner">
                <QrCode className="w-28 h-28 text-slate-950" />
              </div>
              <div className="text-xs font-mono font-bold text-amber-400 mt-3 tracking-widest">
                AUTH TOKEN: #9842-8812-4401
              </div>
              <p className="text-[11px] text-slate-400 mt-1 max-w-xs">
                {isVehicle
                  ? "Present this QR pass to the dealer at vehicle handover. Only once scanned will the escrow release final payment."
                  : "Carrier dispatch order confirmed. Tracking updates will stream in real time."}
              </p>
            </div>

            <button
              onClick={onClose}
              className="w-full h-11 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl transition-all"
            >
              Close & View in My Garage
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
