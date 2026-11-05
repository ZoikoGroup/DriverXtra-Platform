"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  WorkshopProfilePublic,
  WorkshopBooking,
  WorkshopQuotation,
  WorkshopDepositSessionResponse,
  GarageVehicle,
  ChangeOrder,
  PlatformWorkshopReview,
  WorkshopReputationSummary,
} from "@/lib/api/client";
import {
  Wrench,
  Search,
  MapPin,
  Calendar,
  Clock,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  ChevronRight,
  RefreshCw,
  Shield,
  Star,
  MessageSquare,
  X,
  CreditCard,
  Lock,
} from "lucide-react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { WorkshopChatModal } from "./WorkshopChatModal";

export type WorkshopDepositUIState =
  | "required"
  | "initiated"
  | "processing"
  | "paid_and_verified"
  | "failed"
  | "cancelled";

interface RazorpaySuccessResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

interface RazorpayErrorResponse {
  error?: {
    code?: string;
    description?: string;
    source?: string;
    step?: string;
    reason?: string;
    metadata?: {
      payment_id?: string;
      order_id?: string;
    };
  };
}

interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  notes?: Record<string, string>;
  theme?: {
    color?: string;
  };
  modal?: {
    confirm_close?: boolean;
    ondismiss?: () => void;
  };
  handler?: (response: RazorpaySuccessResponse) => void | Promise<void>;
}

export interface RazorpayInstance {
  open: () => void;
  on: (event: string, handler: (resp: RazorpayErrorResponse) => void) => void;
}

function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") {
      resolve(false);
      return;
    }
    if (window.Razorpay) {
      resolve(true);
      return;
    }
    const existing = document.getElementById("razorpay-checkout-js");
    if (existing) {
      if (window.Razorpay) {
        resolve(true);
      } else {
        existing.addEventListener("load", () => resolve(true));
        existing.addEventListener("error", () => resolve(false));
      }
      return;
    }
    const script = document.createElement("script");
    script.id = "razorpay-checkout-js";
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

function getDefaultBookingDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 2);
  return d.toISOString().split("T")[0];
}

export default function BuyerWorkshopsView({ onNavigateToGarage }: { onNavigateToGarage?: () => void }) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"browse" | "my_bookings">("browse");

  // Workshop Browsing State
  const [workshops, setWorkshops] = useState<WorkshopProfilePublic[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [cityFilter, setCityFilter] = useState("");
  const [loadingWorkshops, setLoadingWorkshops] = useState(true);

  // Garage Vehicles
  const [vehicles, setVehicles] = useState<GarageVehicle[]>([]);

  // Booking Modal State
  const [bookingModalOpen, setBookingModalOpen] = useState(false);
  const [targetWorkshop, setTargetWorkshop] = useState<WorkshopProfilePublic | null>(null);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>("");
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([]);
  const [preferredDate, setPreferredDate] = useState<string>("");
  const [preferredTimeSlot, setPreferredTimeSlot] = useState<string>("09:00 - 11:00");
  const [customerNotes, setCustomerNotes] = useState("");
  const [reportedFaults, setReportedFaults] = useState("");
  const [submittingBooking, setSubmittingBooking] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [bookingSuccessNumber, setBookingSuccessNumber] = useState<string | null>(null);

  // My Bookings State
  const [myBookings, setMyBookings] = useState<WorkshopBooking[]>([]);
  const [loadingBookings, setLoadingBookings] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Quotation Response State
  const [respondingQuoteId, setRespondingQuoteId] = useState<string | null>(null);
  const [rejectReasonModal, setRejectReasonModal] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  // Change Orders State for Bookings
  const [bookingChangeOrders, setBookingChangeOrders] = useState<Record<string, ChangeOrder[]>>({});
  const [activeChangeOrderModal, setActiveChangeOrderModal] = useState<ChangeOrder | null>(null);
  const [coActionLoading, setCoActionLoading] = useState(false);
  const [coApprovalNotes, setCoApprovalNotes] = useState("");
  const [coRejectReasonModal, setCoRejectReasonModal] = useState<string | null>(null);
  const [coRejectReason, setCoRejectReason] = useState("");

  // Workshop Reviews Drawer state
  const [reviewsDrawerOpen, setReviewsDrawerOpen] = useState(false);
  const [selectedWorkshopForReviews, setSelectedWorkshopForReviews] = useState<WorkshopProfilePublic | null>(null);
  const [workshopReviewsList, setWorkshopReviewsList] = useState<PlatformWorkshopReview[]>([]);
  const [workshopReputation, setWorkshopReputation] = useState<WorkshopReputationSummary | null>(null);
  const [loadingWorkshopReviews, setLoadingWorkshopReviews] = useState(false);
  const [workshopReviewsError, setWorkshopReviewsError] = useState<string | null>(null);

  // Review Submission Modal state
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [targetBookingForReview, setTargetBookingForReview] = useState<WorkshopBooking | null>(null);
  const [reviewRating, setReviewRating] = useState<number>(5);
  const [reviewHoverRating, setReviewHoverRating] = useState<number>(0);
  const [reviewCommRating, setReviewCommRating] = useState<number>(5);
  const [reviewWorkRating, setReviewWorkRating] = useState<number>(5);
  const [reviewPriceRating, setReviewPriceRating] = useState<number>(5);
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewSuccess, setReviewSuccess] = useState<string | null>(null);

  // Authoritative Deposit Payment Modal & UI State
  const [depositModalOpen, setDepositModalOpen] = useState(false);
  const [targetBookingForDeposit, setTargetBookingForDeposit] = useState<WorkshopBooking | null>(null);
  const [targetQuotationForDeposit, setTargetQuotationForDeposit] = useState<WorkshopQuotation | null>(null);
  const [depositSession, setDepositSession] = useState<WorkshopDepositSessionResponse | null>(null);
  const [depositUIState, setDepositUIState] = useState<WorkshopDepositUIState>("required");
  const [depositError, setDepositError] = useState<string | null>(null);
  const [depositSuccess, setDepositSuccess] = useState<string | null>(null);

  // Workshop Messaging State
  const [chatModalOpen, setChatModalOpen] = useState(false);
  const [targetBookingForChat, setTargetBookingForChat] = useState<WorkshopBooking | null>(null);

  const openChatModal = (bk: WorkshopBooking) => {
    setTargetBookingForChat(bk);
    setChatModalOpen(true);
  };

  const depositLoading = depositUIState === "initiated" && !depositSession;

  const openWorkshopReviews = async (ws: WorkshopProfilePublic) => {
    setSelectedWorkshopForReviews(ws);
    setReviewsDrawerOpen(true);
    setLoadingWorkshopReviews(true);
    setWorkshopReviewsError(null);
    try {
      const res = await api.workshops.reviews.list(ws.slug || ws.id);
      setWorkshopReviewsList(res.results || []);
      setWorkshopReputation(res.reputation || null);
    } catch (err) {
      setWorkshopReviewsError(err instanceof Error ? err.message : "Failed to load customer reviews.");
    } finally {
      setLoadingWorkshopReviews(false);
    }
  };

  const openReviewModal = (bk: WorkshopBooking) => {
    setTargetBookingForReview(bk);
    setReviewRating(5);
    setReviewHoverRating(0);
    setReviewCommRating(5);
    setReviewWorkRating(5);
    setReviewPriceRating(5);
    setReviewTitle("");
    setReviewComment("");
    setReviewError(null);
    setReviewSuccess(null);
    setReviewModalOpen(true);
  };

  const fetchMyBookings = useCallback(async () => {
    setLoadingBookings(true);
    try {
      const res = await api.workshops.listMyBookings({ status: statusFilter || undefined });
      const bookings = res.results || [];
      setMyBookings(bookings);
      const coMap: Record<string, ChangeOrder[]> = {};
      await Promise.all(
        bookings.map(async (b) => {
          try {
            const coRes = await api.workshops.listBuyerChangeOrders(b.id);
            if (coRes.results && coRes.results.length > 0) {
              coMap[b.id] = coRes.results;
            }
          } catch {
            // ignore
          }
        })
      );
      setBookingChangeOrders(coMap);
    } catch (err) {
      console.error("Failed to load my bookings:", err);
    } finally {
      setLoadingBookings(false);
    }
  }, [statusFilter]);

  // =========================================================================
  // REAL GATEWAY DEPOSIT CHECKOUT ORCHESTRATION (RAZORPAY & STRIPE)
  // =========================================================================

  const openDepositModal = async (bk: WorkshopBooking, quote: WorkshopQuotation) => {
    // 1. Prevent duplicate checkout initiation while payment is in-flight
    if (depositUIState === "initiated" || depositUIState === "processing") {
      return;
    }

    setTargetBookingForDeposit(bk);
    setTargetQuotationForDeposit(quote);
    setDepositModalOpen(true);
    setDepositUIState("initiated");
    setDepositError(null);
    setDepositSuccess(null);
    setDepositSession(null);

    try {
      const returnUrl =
        typeof window !== "undefined"
          ? `${window.location.origin}/platform?tab=workshops&deposit_quote_id=${quote.id}`
          : undefined;
      const cancelUrl =
        typeof window !== "undefined"
          ? `${window.location.origin}/platform?tab=workshops&deposit_cancelled=true`
          : undefined;

      const session = await api.workshops.createDepositSession(quote.id, {
        return_url: returnUrl,
        cancel_url: cancelUrl,
      });
      setDepositSession(session);

      const provider = (
        session.payment_session?.provider ||
        (quote.currency === "GBP" ? "STRIPE" : "RAZORPAY")
      ).toUpperCase();

      if (provider === "RAZORPAY") {
        const loaded = await loadRazorpayScript();
        if (!loaded || !window.Razorpay) {
          setDepositUIState("failed");
          setDepositError("Unable to load Razorpay Checkout SDK. Please check your network connection and retry.");
          return;
        }

        const RazorpayClass = window.Razorpay;
        const options: RazorpayOptions = {
          key:
            session.payment_session.key_id ||
            process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID ||
            "rzp_test_placeholder_key",
          amount:
            session.payment_session.amount_minor ||
            Math.round(parseFloat(quote.deposit_amount || "0") * 100),
          currency: session.currency || quote.currency || "INR",
          name: "DriverXtra Platform",
          description: `Quotation Deposit #${quote.quotation_number} (${bk.workshop_name})`,
          order_id: session.payment_session.provider_order_id,
          prefill: {
            name: user?.fullName || "",
            email: user?.email || "",
          },
          notes: {
            quotation_id: quote.id,
            quotation_number: quote.quotation_number,
            booking_number: bk.booking_number,
          },
          theme: {
            color: "#f59e0b",
          },
          handler: async function (response: RazorpaySuccessResponse) {
            setDepositUIState("processing");
            setDepositError(null);
            try {
              const verifyRes = await api.workshops.verifyDeposit(quote.id, {
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                amount: quote.deposit_amount,
                currency: quote.currency,
              });

              if (verifyRes.status === "success" || verifyRes.quotation?.deposit_status === "PAID") {
                setDepositUIState("paid_and_verified");
                setDepositSuccess("Deposit payment verified! Your quotation is accepted and booking is confirmed.");
                setActionSuccessMessage("Deposit paid successfully! Your workshop booking is confirmed.");
                await fetchMyBookings();
              } else {
                setDepositUIState("failed");
                setDepositError(verifyRes.message || "Deposit verification failed.");
              }
            } catch (vErr: unknown) {
              setDepositUIState("failed");
              setDepositError(vErr instanceof Error ? vErr.message : "Deposit verification failed.");
            }
          },
          modal: {
            confirm_close: true,
            ondismiss: function () {
              setDepositUIState("cancelled");
              setDepositError("Payment checkout was cancelled or dismissed. Your quotation remains reserved and ready.");
            },
          },
        };

        const rzp = new RazorpayClass(options);
        rzp.on("payment.failed", function (resp: RazorpayErrorResponse) {
          setDepositUIState("failed");
          const desc = resp?.error?.description || "Payment failed or was declined.";
          setDepositError(`Payment failed: ${desc}. Please retry or choose another payment method.`);
        });
        rzp.open();
      } else if (provider === "STRIPE") {
        if (session.payment_session?.checkout_url) {
          setDepositUIState("processing");
          window.location.assign(session.payment_session.checkout_url);
        }
      }
    } catch (err: unknown) {
      setDepositUIState("failed");
      setDepositError(err instanceof Error ? err.message : "Failed to initiate deposit payment session.");
    }
  };

  const handleConfirmDepositPayment = async () => {
    if (!targetQuotationForDeposit || !depositSession) return;
    if (depositUIState === "processing") return;

    setDepositUIState("processing");
    setDepositError(null);

    try {
      const pSession = depositSession.payment_session;
      const provider = (
        pSession.provider ||
        (targetQuotationForDeposit.currency === "GBP" ? "STRIPE" : "RAZORPAY")
      ).toUpperCase();

      if (provider === "STRIPE") {
        const verifyPayload = {
          payment_intent_id: pSession.provider_order_id,
          stripe_payment_intent_id: pSession.provider_order_id,
          client_secret: pSession.client_secret,
          amount: targetQuotationForDeposit.deposit_amount,
          currency: targetQuotationForDeposit.currency,
        };

        const res = await api.workshops.verifyDeposit(targetQuotationForDeposit.id, verifyPayload);
        if (res.status === "success" || res.quotation?.deposit_status === "PAID") {
          setDepositUIState("paid_and_verified");
          setDepositSuccess("Stripe deposit confirmed & verified! Your quotation is accepted and booking is confirmed.");
          setActionSuccessMessage("Deposit paid successfully! Your workshop booking is confirmed.");
          await fetchMyBookings();
        } else {
          setDepositUIState("failed");
          setDepositError(res.message || "Stripe deposit verification failed.");
        }
      } else {
        const loaded = await loadRazorpayScript();
        if (!loaded || !window.Razorpay) {
          setDepositUIState("failed");
          setDepositError("Unable to load Razorpay Checkout SDK. Please check your network connection.");
          return;
        }
        const RazorpayClass = window.Razorpay;
        const options: RazorpayOptions = {
          key: pSession.key_id || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID || "rzp_test_placeholder_key",
          amount: pSession.amount_minor || Math.round(parseFloat(targetQuotationForDeposit.deposit_amount || "0") * 100),
          currency: targetQuotationForDeposit.currency,
          name: "DriverXtra Platform",
          description: `Quotation Deposit #${targetQuotationForDeposit.quotation_number}`,
          order_id: pSession.provider_order_id,
          prefill: {
            name: user?.fullName || "",
            email: user?.email || "",
          },
          notes: {
            quotation_id: targetQuotationForDeposit.id,
            quotation_number: targetQuotationForDeposit.quotation_number,
          },
          theme: { color: "#f59e0b" },
          handler: async function (response: RazorpaySuccessResponse) {
            setDepositUIState("processing");
            try {
              const res = await api.workshops.verifyDeposit(targetQuotationForDeposit.id, {
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                amount: targetQuotationForDeposit.deposit_amount,
                currency: targetQuotationForDeposit.currency,
              });
              if (res.status === "success" || res.quotation?.deposit_status === "PAID") {
                setDepositUIState("paid_and_verified");
                setDepositSuccess("Deposit payment verified! Your quotation is accepted and booking is confirmed.");
                setActionSuccessMessage("Deposit paid successfully! Your workshop booking is confirmed.");
                await fetchMyBookings();
              } else {
                setDepositUIState("failed");
                setDepositError(res.message || "Deposit verification failed.");
              }
            } catch (vErr: unknown) {
              setDepositUIState("failed");
              setDepositError(vErr instanceof Error ? vErr.message : "Deposit verification failed.");
            }
          },
          modal: {
            confirm_close: true,
            ondismiss: function () {
              setDepositUIState("cancelled");
              setDepositError("Payment checkout was cancelled or dismissed. Quotation remains pending deposit.");
            },
          },
        };
        const rzp = new RazorpayClass(options);
        rzp.on("payment.failed", function (resp: RazorpayErrorResponse) {
          setDepositUIState("failed");
          const desc = resp?.error?.description || "Payment failed.";
          setDepositError(`Payment failed: ${desc}`);
        });
        rzp.open();
      }
    } catch (err: unknown) {
      setDepositUIState("failed");
      setDepositError(err instanceof Error ? err.message : "Deposit payment failed.");
    }
  };

  // Authoritative URL Return Handler (Stripe Return / Callback / Cancelled)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const searchParams = new URLSearchParams(window.location.search);
    const depositQuoteId = searchParams.get("deposit_quote_id");
    const paymentIntent = searchParams.get("payment_intent") || searchParams.get("payment_intent_id");
    const depositCancelled = searchParams.get("deposit_cancelled");

    if (depositCancelled === "true") {
      const cleanUrl = window.location.pathname + (window.location.hash || "");
      window.history.replaceState({}, document.title, cleanUrl);
      queueMicrotask(() => {
        setDepositUIState("cancelled");
        setDepositError("Stripe checkout was cancelled. You can retry payment whenever you are ready.");
      });
      return;
    }

    if (depositQuoteId) {
      // NEVER trust URL query parameters alone as confirmation!
      // Must query backend verification endpoint authoritatively.
      queueMicrotask(() => {
        setDepositUIState("processing");
        setDepositModalOpen(true);
      });

      api.workshops
        .verifyDeposit(depositQuoteId, {
          payment_intent_id: paymentIntent || undefined,
        })
        .then((res) => {
          if (res.status === "success" || res.quotation?.deposit_status === "PAID") {
            setDepositUIState("paid_and_verified");
            setDepositSuccess("Stripe deposit confirmed & verified! Your booking is confirmed.");
            setActionSuccessMessage("Stripe deposit confirmed! Your booking is confirmed.");
            fetchMyBookings();
          } else {
            setDepositUIState("failed");
            setDepositError(res.message || "Failed to authoritatively confirm payment with Stripe.");
          }
        })
        .catch((err) => {
          api.workshops
            .getDepositDetails(depositQuoteId)
            .then((details) => {
              if (details.deposit_status === "PAID") {
                setDepositUIState("paid_and_verified");
                setDepositSuccess("Deposit verified! Your booking is confirmed.");
                fetchMyBookings();
              } else {
                setDepositUIState("failed");
                setDepositError(err instanceof Error ? err.message : "Authoritative payment verification failed.");
              }
            })
            .catch(() => {
              setDepositUIState("failed");
              setDepositError(err instanceof Error ? err.message : "Authoritative payment verification failed.");
            });
        })
        .finally(() => {
          const cleanUrl = window.location.pathname + (window.location.hash || "");
          window.history.replaceState({}, document.title, cleanUrl);
        });
    }
  }, [fetchMyBookings]);

  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetBookingForReview) return;
    if (reviewRating < 1 || reviewRating > 5) {
      setReviewError("Please select a rating between 1 and 5 stars.");
      return;
    }
    if (reviewComment.trim().length < 5) {
      setReviewError("Review comment must be at least 5 characters long.");
      return;
    }

    setSubmittingReview(true);
    setReviewError(null);
    try {
      await api.workshops.reviews.create(targetBookingForReview.id, {
        rating: reviewRating,
        title: reviewTitle.trim() || undefined,
        comment: reviewComment.trim(),
        communication_rating: reviewCommRating || undefined,
        workmanship_rating: reviewWorkRating || undefined,
        pricing_transparency_rating: reviewPriceRating || undefined,
      });

      setReviewSuccess("Thank you! Your verified workshop review has been published.");
      fetchMyBookings();
      setTimeout(() => {
        setReviewModalOpen(false);
        setReviewSuccess(null);
      }, 1500);
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : "Failed to submit review.");
    } finally {
      setSubmittingReview(false);
    }
  };

  // Load workshops
  useEffect(() => {
    let ignore = false;
    api.workshops
      .list({
        q: searchQuery || undefined,
        city: cityFilter || undefined,
        accepting_only: true,
      })
      .then((res) => {
        if (!ignore) {
          setWorkshops(res.results || []);
          setLoadingWorkshops(false);
        }
      })
      .catch((err) => {
        console.error("Failed to load workshops:", err);
        if (!ignore) setLoadingWorkshops(false);
      });
    return () => {
      ignore = true;
    };
  }, [searchQuery, cityFilter]);

  // Load vehicles
  useEffect(() => {
    let ignore = false;
    api.garage
      .listVehicles()
      .then((res) => {
        if (!ignore) {
          const active = (res || []).filter((v: GarageVehicle) => !v.is_archived);
          setVehicles(active);
          if (active.length > 0) {
            setSelectedVehicleId((prev) => prev || active[0].id);
          }
        }
      })
      .catch((err) => {
        console.error("Failed to load garage vehicles:", err);
      });
    return () => {
      ignore = true;
    };
  }, []);

  // Load my bookings when tab changes
  useEffect(() => {
    if (activeTab === "my_bookings") {
      let ignore = false;
      api.workshops
        .listMyBookings({ status: statusFilter || undefined })
        .then(async (res) => {
          if (!ignore) {
            const bookings = res.results || [];
            setMyBookings(bookings);
            const coMap: Record<string, ChangeOrder[]> = {};
            await Promise.all(
              bookings.map(async (b) => {
                try {
                  const coRes = await api.workshops.listBuyerChangeOrders(b.id);
                  if (coRes.results && coRes.results.length > 0) {
                    coMap[b.id] = coRes.results;
                  }
                } catch {
                  // ignore
                }
              })
            );
            if (!ignore) {
              setBookingChangeOrders(coMap);
              setLoadingBookings(false);
            }
          }
        })
        .catch((err) => {
          console.error("Failed to load my bookings:", err);
          if (!ignore) setLoadingBookings(false);
        });
      return () => {
        ignore = true;
      };
    }
  }, [activeTab, statusFilter]);

  const openBookingModal = (ws: WorkshopProfilePublic) => {
    setTargetWorkshop(ws);
    setSelectedServiceIds([]);
    setPreferredDate(getDefaultBookingDate());
    setPreferredTimeSlot("09:00 - 11:00");
    setCustomerNotes("");
    setReportedFaults("");
    setBookingError(null);
    setBookingSuccessNumber(null);
    setBookingModalOpen(true);
  };

  const handleToggleService = (serviceId: string) => {
    setSelectedServiceIds((prev) =>
      prev.includes(serviceId) ? prev.filter((id) => id !== serviceId) : [...prev, serviceId]
    );
  };

  const handleCreateBooking = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetWorkshop) return;
    if (!selectedVehicleId) {
      setBookingError("Please select a registered garage vehicle.");
      return;
    }
    if (!preferredDate) {
      setBookingError("Please select a preferred appointment date.");
      return;
    }

    setSubmittingBooking(true);
    setBookingError(null);

    try {
      const booking = await api.workshops.createBooking({
        workshop_id: targetWorkshop.id,
        vehicle_id: selectedVehicleId,
        service_ids: selectedServiceIds,
        preferred_date: preferredDate,
        preferred_time_slot: preferredTimeSlot,
        customer_notes: customerNotes,
        reported_faults: reportedFaults,
      });

      setBookingSuccessNumber(booking.booking_number);
      fetchMyBookings();
    } catch (err: unknown) {
      setBookingError(err instanceof Error ? err.message : "Failed to submit booking request.");
    } finally {
      setSubmittingBooking(false);
    }
  };

  const handleAcceptQuotation = async (quoteId: string) => {
    setRespondingQuoteId(quoteId);
    try {
      await api.workshops.acceptQuotation(quoteId);
      setActionSuccessMessage("Quotation accepted successfully! Your appointment is confirmed.");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to accept quotation.");
    } finally {
      setRespondingQuoteId(null);
    }
  };

  const handleRejectQuotation = async () => {
    if (!rejectReasonModal) return;
    setRespondingQuoteId(rejectReasonModal);
    try {
      await api.workshops.rejectQuotation(rejectReasonModal, rejectReason);
      setActionSuccessMessage("Quotation rejected. The workshop has been notified.");
      setRejectReasonModal(null);
      setRejectReason("");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to reject quotation.");
    } finally {
      setRespondingQuoteId(null);
    }
  };

  const handleCancelBooking = async (bookingId: string) => {
    const reason = prompt("Please provide a reason for cancelling this booking:");
    if (!reason || !reason.trim()) return;

    try {
      await api.workshops.cancelMyBooking(bookingId, reason);
      setActionSuccessMessage("Booking cancelled successfully.");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to cancel booking.");
    }
  };

  const handleApproveChangeOrder = async (coId: string) => {
    setCoActionLoading(true);
    try {
      await api.workshops.approveChangeOrder(coId, coApprovalNotes);
      setActionSuccessMessage("Change order authorized successfully.");
      setActiveChangeOrderModal(null);
      setCoApprovalNotes("");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to approve change order.");
    } finally {
      setCoActionLoading(false);
    }
  };

  const handleRejectChangeOrder = async () => {
    if (!coRejectReasonModal) return;
    setCoActionLoading(true);
    try {
      await api.workshops.rejectChangeOrder(coRejectReasonModal, coRejectReason);
      setActionSuccessMessage("Change order declined.");
      setCoRejectReasonModal(null);
      setActiveChangeOrderModal(null);
      setCoRejectReason("");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to decline change order.");
    } finally {
      setCoActionLoading(false);
    }
  };

  // Status helper colors
  const getStatusBadge = (status: string) => {
    switch (status) {
      case "CONFIRMED":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "ACCEPTED":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "QUOTED":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "REQUESTED":
      case "UNDER_REVIEW":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "CANCELLED":
      case "REJECTED":
        return "bg-rose-50 text-rose-700 border-rose-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-950 text-white rounded-3xl p-6 shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-amber-400/10 text-amber-400 text-xs font-bold border border-amber-400/20 mb-2">
            <Wrench className="w-3.5 h-3.5" />
            <span>DriverXtra Verified Service Network</span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">Workshop Services & Bookings</h1>
          <p className="text-xs text-slate-400 max-w-xl mt-1">
            Browse verified automotive service centres, request bookings with your garage vehicle, and review certified quotations with transparent pricing.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-2 bg-slate-900 p-1.5 rounded-2xl border border-slate-800 self-start md:self-auto">
          <button
            onClick={() => setActiveTab("browse")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "browse"
                ? "bg-amber-400 text-slate-950 shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Find Workshops
          </button>
          <button
            onClick={() => setActiveTab("my_bookings")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
              activeTab === "my_bookings"
                ? "bg-amber-400 text-slate-950 shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <span>My Bookings</span>
            {myBookings.length > 0 && (
              <span className="w-5 h-5 rounded-full bg-slate-950 text-amber-400 text-[10px] font-black flex items-center justify-center">
                {myBookings.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {actionSuccessMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl text-xs font-bold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{actionSuccessMessage}</span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: BROWSE WORKSHOPS */}
      {/* ========================================================================= */}
      {activeTab === "browse" && (
        <div className="space-y-6">
          {/* Search & Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3 items-center">
            <div className="relative flex-1 w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search by workshop name, service, or keyword..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
            <div className="relative w-full md:w-56">
              <MapPin className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Filter by city (e.g. London)"
                value={cityFilter}
                onChange={(e) => setCityFilter(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
          </div>

          {/* Workshop Cards Grid */}
          {loadingWorkshops ? (
            <div className="p-12 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
              <span>Locating verified service centres...</span>
            </div>
          ) : workshops.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200 space-y-2">
              <Wrench className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-black text-slate-900">No workshops match your criteria</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Try removing city filters or search terms. Only verified workshops currently accepting bookings are displayed.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {workshops.map((ws) => (
                <div
                  key={ws.id}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all p-5 flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <h3 className="text-sm font-black text-slate-950">{ws.display_name}</h3>
                          {ws.is_verified && (
                            <span title="Verified Workshop"><Shield className="w-3.5 h-3.5 text-emerald-600 shrink-0" /></span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-0.5">
                          <MapPin className="w-3 h-3 text-slate-400" />
                          <span>{ws.city || "UK"}, {ws.country}</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1.5">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                          {ws.bay_capacity} Bays
                        </span>
                        <button
                          type="button"
                          onClick={() => openWorkshopReviews(ws)}
                          className="flex items-center gap-1 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-200/80 px-2 py-0.5 rounded-full text-[10px] font-bold transition-colors cursor-pointer"
                          title="Click to view customer reviews"
                        >
                          <Star className="w-3 h-3 text-amber-500 fill-amber-500 shrink-0" />
                          <span>{ws.average_rating && ws.average_rating > 0 ? Number(ws.average_rating).toFixed(1) : "New"}</span>
                          {ws.review_count && ws.review_count > 0 ? (
                            <span className="text-amber-700 font-medium">({ws.review_count})</span>
                          ) : null}
                        </button>
                      </div>
                    </div>

                    {ws.description && (
                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                        {ws.description}
                      </p>
                    )}

                    {/* Services Preview */}
                    <div className="space-y-1.5 pt-2 border-t border-slate-100">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Popular Services ({ws.services?.length || 0})
                      </span>
                      {ws.services && ws.services.length > 0 ? (
                        <div className="space-y-1">
                          {ws.services.slice(0, 3).map((srv) => (
                            <div key={srv.id} className="flex items-center justify-between text-xs">
                              <span className="text-slate-700 font-medium truncate max-w-[180px]">{srv.name}</span>
                              <span className="text-slate-900 font-bold">{srv.currency} {srv.base_price}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Price upon inspection / quotation</span>
                      )}
                    </div>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-100 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => openWorkshopReviews(ws)}
                      className="py-2.5 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                    >
                      <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                      <span>Reviews</span>
                    </button>
                    <button
                      onClick={() => openBookingModal(ws)}
                      className="flex-1 py-2.5 px-3 bg-slate-950 hover:bg-slate-900 text-white font-bold text-xs rounded-xl transition-all flex items-center justify-center gap-1.5 shadow-sm"
                    >
                      <span>Book Service</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: MY BOOKINGS & QUOTATIONS */}
      {/* ========================================================================= */}
      {activeTab === "my_bookings" && (
        <div className="space-y-6">
          {/* Status Filter Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {["", "REQUESTED", "ACCEPTED", "CONFIRMED", "QUOTED", "CANCELLED"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all border ${
                  statusFilter === st
                    ? "bg-slate-950 text-white border-slate-950"
                    : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                }`}
              >
                {st === "" ? "All Bookings" : st.replace("_", " ")}
              </button>
            ))}
          </div>

          {loadingBookings ? (
            <div className="p-12 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
              <span>Loading your booking history...</span>
            </div>
          ) : myBookings.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200 space-y-3">
              <Calendar className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-black text-slate-900">No bookings found</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                You haven&apos;t booked any workshop appointments yet. Browse verified centres to schedule your service.
              </p>
              <button
                onClick={() => setActiveTab("browse")}
                className="mt-2 px-4 py-2 bg-amber-400 text-slate-950 font-bold text-xs rounded-xl hover:bg-amber-500 transition-all"
              >
                Find a Workshop
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {myBookings.map((bk) => (
                <div
                  key={bk.id}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4"
                >
                  {/* Top Line */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-700 flex items-center justify-center font-black text-xs shrink-0">
                        <Wrench className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-black text-slate-900">{bk.booking_number}</span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusBadge(
                              bk.status
                            )}`}
                          >
                            {bk.status}
                          </span>
                          {bk.active_quotation?.status === "ISSUED" && (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1.5 shadow-xs">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                              Quotation Ready for Review
                            </span>
                          )}
                          {bk.active_quotation?.status === "ACCEPTED" && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                              Quote Accepted
                            </span>
                          )}
                        </div>
                        <h4 className="text-sm font-black text-slate-950 mt-0.5">{bk.workshop_name}</h4>
                      </div>
                    </div>

                    <div className="text-right text-xs">
                      <span className="text-slate-400 block text-[11px]">Preferred Date</span>
                      <span className="font-bold text-slate-900">
                        {bk.preferred_date} {bk.preferred_time_slot && `(${bk.preferred_time_slot})`}
                      </span>
                    </div>
                  </div>

                  {/* Vehicle & Fault Details */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs bg-slate-50 p-4 rounded-xl">
                    <div>
                      <span className="text-slate-400 text-[11px] font-bold uppercase block">Vehicle</span>
                      <span className="font-bold text-slate-900">
                        {bk.vehicle_make} {bk.vehicle_model} ({bk.vehicle_year || "N/A"})
                      </span>
                      <span className="block text-slate-600 font-mono mt-0.5">{bk.vehicle_registration_plate}</span>
                    </div>

                    <div>
                      <span className="text-slate-400 text-[11px] font-bold uppercase block">Scheduled Appointment</span>
                      {bk.scheduled_appointment_start ? (
                        <div className="text-emerald-700 font-bold flex items-center gap-1.5 mt-0.5">
                          <Clock className="w-3.5 h-3.5" />
                          <span>
                            {new Date(bk.scheduled_appointment_start).toLocaleDateString("en-GB", {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-500 italic mt-0.5 block">Awaiting workshop confirmation</span>
                      )}
                    </div>

                    <div>
                      <span className="text-slate-400 text-[11px] font-bold uppercase block">Contact Workshop</span>
                      <span className="text-slate-700 block font-medium">{bk.workshop_phone || bk.workshop_email || "N/A"}</span>
                      <span className="text-slate-500 text-[11px]">{bk.workshop_city}</span>
                    </div>
                  </div>

                  {bk.reported_faults && (
                    <div className="text-xs text-slate-700 bg-amber-50/60 border border-amber-200/60 p-3 rounded-xl">
                      <span className="font-bold text-amber-900 block">Reported Faults & Symptoms:</span>
                      <p className="mt-0.5">{bk.reported_faults}</p>
                    </div>
                  )}

                  {/* Change Orders & Additional Scope Requests (Buyer Review) */}
                  {bookingChangeOrders[bk.id] && bookingChangeOrders[bk.id].length > 0 && (
                    <div className="space-y-3">
                      {/* Pending Change Orders Requiring Buyer Decision */}
                      {bookingChangeOrders[bk.id].filter(c => c.status === "SUBMITTED").map((co) => (
                        <div
                          key={co.id}
                          className="p-4 rounded-2xl bg-gradient-to-r from-amber-50 to-orange-50 border-2 border-amber-300 text-amber-950 space-y-3 shadow-xs"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="flex items-start gap-2.5">
                              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] font-black uppercase tracking-wider bg-amber-200 text-amber-900 px-2 py-0.5 rounded border border-amber-300">
                                    Action Required
                                  </span>
                                  <span className="font-mono text-xs font-bold text-slate-700">
                                    Change Order #{co.change_order_number}
                                  </span>
                                </div>
                                <h5 className="font-black text-sm text-slate-900 mt-0.5">
                                  Workshop Requested Additional Repair Authorization
                                </h5>
                                <p className="text-xs text-slate-700 mt-1">
                                  <strong className="text-slate-900">Diagnosis: </strong>
                                  {co.reason}
                                </p>
                              </div>
                            </div>
                            <div className="text-right sm:border-l sm:border-amber-200 sm:pl-4 shrink-0">
                              <span className="text-[10px] text-slate-500 block uppercase font-bold">Additional Cost</span>
                              <span className="text-lg font-black text-purple-700">
                                +{co.currency} {parseFloat(co.additional_amount).toFixed(2)}
                              </span>
                              <span className="text-[10px] text-slate-500 block font-mono">
                                Revised Total: {co.currency} {parseFloat(co.revised_authorized_total).toFixed(2)}
                              </span>
                              <button
                                type="button"
                                onClick={() => setActiveChangeOrderModal(co)}
                                className="mt-2 w-full px-4 py-2 bg-amber-500 hover:bg-amber-600 text-slate-950 font-black text-xs rounded-xl transition shadow-xs flex items-center justify-center gap-1.5"
                              >
                                <span>Review & Authorize</span>
                                <ChevronRight className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}

                      {/* Historical Decided Change Orders */}
                      {bookingChangeOrders[bk.id].filter(c => c.status !== "SUBMITTED").length > 0 && (
                        <div className="bg-slate-50 rounded-2xl p-3 border border-slate-200 space-y-2 text-xs">
                          <span className="font-bold text-slate-700 block text-[11px] uppercase tracking-wider">
                            Additional Repair Authorization History
                          </span>
                          <div className="space-y-1.5">
                            {bookingChangeOrders[bk.id].filter(c => c.status !== "SUBMITTED").map((co) => (
                              <div
                                key={co.id}
                                className="flex items-center justify-between p-2 rounded-xl bg-white border border-slate-200"
                              >
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                                      co.status === "APPROVED"
                                        ? "bg-emerald-100 text-emerald-800"
                                        : "bg-rose-100 text-rose-800"
                                    }`}
                                  >
                                    {co.status === "APPROVED" ? "Authorized" : "Declined"}
                                  </span>
                                  <span className="font-mono font-bold text-slate-800">#{co.change_order_number}</span>
                                  <span className="text-slate-600 truncate max-w-xs">{co.reason}</span>
                                </div>
                                <div className="text-right">
                                  <span className="font-bold text-slate-900 font-mono">
                                    {co.status === "APPROVED" ? `+${co.currency} ${co.additional_amount}` : "Declined"}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                                    {/* Quotation Review Card (If Quotation Available) */}
                  {bk.active_quotation && (
                    <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 to-purple-950 text-white space-y-4 shadow-sm border border-slate-800">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 pb-3 border-b border-white/10">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-black uppercase tracking-wider text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded border border-amber-400/20">
                              Official Workshop Quotation
                            </span>
                            <span className="text-xs text-slate-300">
                              #{bk.active_quotation.quotation_number} (v{bk.active_quotation.version})
                            </span>
                          </div>
                          <h4 className="text-base font-black mt-1">Estimate Breakdown & Scope of Work</h4>
                        </div>
                        <div className="text-right">
                          <span className="text-xs text-slate-400 block">Final Quoted Total</span>
                          <span className="text-xl font-black text-amber-400">
                            {bk.active_quotation.currency} {bk.active_quotation.total_amount}
                          </span>
                        </div>
                      </div>

                      {/* Quotation Line Items Table */}
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="text-slate-400 border-b border-white/10 text-[11px] uppercase tracking-wider">
                              <th className="pb-2">Type</th>
                              <th className="pb-2">Description / Part</th>
                              <th className="pb-2 text-center">Qty</th>
                              <th className="pb-2 text-right">Unit Price</th>
                              <th className="pb-2 text-right">Line Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/5">
                            {bk.active_quotation.line_items.map((item) => (
                              <tr key={item.id} className="text-slate-200">
                                <td className="py-2">
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-white/10 text-slate-300">
                                    {item.item_type_display}
                                  </span>
                                </td>
                                <td className="py-2">
                                  <span className="font-bold">{item.description}</span>
                                  {item.part_number && (
                                    <span className="block text-[10px] text-slate-400 font-mono">
                                      PN: {item.part_number}
                                    </span>
                                  )}
                                </td>
                                <td className="py-2 text-center">{item.quantity}</td>
                                <td className="py-2 text-right">
                                  {bk.active_quotation?.currency} {item.unit_price}
                                </td>
                                <td className="py-2 text-right font-bold text-white">
                                  {bk.active_quotation?.currency} {item.line_total}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Financial Totals Summary */}
                      <div className="pt-3 border-t border-white/10 flex flex-col md:flex-row justify-between text-xs gap-3">
                        <div className="text-slate-400 text-[11px] space-y-1">
                          {bk.active_quotation?.workshop_notes && (
                            <p>
                              <span className="text-slate-300 font-bold">Notes: </span>
                              {bk.active_quotation?.workshop_notes}
                            </p>
                          )}
                          {bk.active_quotation.valid_until && (
                            <p>
                              <span className="text-slate-300 font-bold">Quote Valid Until: </span>
                              {bk.active_quotation.valid_until}
                            </p>
                          )}
                        </div>

                        <div className="w-full md:w-64 space-y-1 text-slate-300">
                          <div className="flex justify-between">
                            <span>Labour Subtotal:</span>
                            <span className="font-medium">
                              {bk.active_quotation.currency} {bk.active_quotation.subtotal_labour}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>Parts Subtotal:</span>
                            <span className="font-medium">
                              {bk.active_quotation.currency} {bk.active_quotation.subtotal_parts}
                            </span>
                          </div>
                          {parseFloat(bk.active_quotation.subtotal_other) > 0 && (
                            <div className="flex justify-between">
                              <span>Diagnostics / Fees:</span>
                              <span className="font-medium">
                                {bk.active_quotation.currency} {bk.active_quotation.subtotal_other}
                              </span>
                            </div>
                          )}
                          {parseFloat(bk.active_quotation.discount_amount) > 0 && (
                            <div className="flex justify-between text-emerald-400">
                              <span>Discount Applied:</span>
                              <span>
                                -{bk.active_quotation.currency} {bk.active_quotation.discount_amount}
                              </span>
                            </div>
                          )}
                          <div className="flex justify-between">
                            <span>VAT / Tax ({bk.active_quotation.tax_rate_percent}%):</span>
                            <span>
                              {bk.active_quotation.currency} {bk.active_quotation.tax_amount}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm font-black text-amber-400 pt-1 border-t border-white/10">
                            <span>Total Quote:</span>
                            <span>
                              {bk.active_quotation.currency} {bk.active_quotation.total_amount}
                            </span>
                          </div>

                          {bk.active_quotation.requires_deposit && (
                            <div className="mt-2 pt-2 border-t border-amber-400/20 bg-amber-400/10 rounded-lg p-2.5 space-y-1">
                              <div className="flex justify-between text-xs text-amber-300 font-bold">
                                <span>Required Upfront Deposit ({bk.active_quotation.deposit_percentage}%):</span>
                                <span>{bk.active_quotation.currency} {bk.active_quotation.deposit_amount}</span>
                              </div>
                              <div className="flex justify-between text-xs text-slate-300">
                                <span>Remaining Balance Due at Workshop:</span>
                                <span>
                                  {bk.active_quotation.currency}{" "}
                                  {(
                                    parseFloat(bk.active_quotation.total_amount) -
                                    parseFloat(bk.active_quotation.deposit_amount || "0")
                                  ).toFixed(2)}
                                </span>
                              </div>
                              <div className="flex justify-between text-[11px] text-slate-400 pt-0.5">
                                <span>Deposit Status:</span>
                                <span
                                  className={`font-black uppercase tracking-wider ${
                                    bk.active_quotation.deposit_status === "PAID"
                                      ? "text-emerald-400"
                                      : bk.active_quotation.deposit_status === "FAILED"
                                      ? "text-rose-400"
                                      : bk.active_quotation.deposit_status === "PROCESSING"
                                      ? "text-sky-400"
                                      : "text-amber-400"
                                  }`}
                                >
                                  {bk.active_quotation.deposit_status === "PAID"
                                    ? "PAID AND VERIFIED"
                                    : bk.active_quotation.deposit_status === "PROCESSING"
                                    ? "PROCESSING"
                                    : bk.active_quotation.deposit_status === "FAILED"
                                    ? "PAYMENT FAILED"
                                    : "PAYMENT REQUIRED"}
                                </span>
                              </div>
                              {bk.active_quotation.deposit_transaction_id && (
                                <div className="text-[10px] text-slate-400 font-mono truncate">
                                  Ref: {bk.active_quotation.deposit_transaction_id}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Quotation Actions */}
                      {bk.active_quotation.status === "ISSUED" && (
                        <div className="pt-3 border-t border-white/10 flex items-center justify-end gap-3">
                          <button
                            onClick={() => setRejectReasonModal(bk.active_quotation!.id)}
                            disabled={respondingQuoteId === bk.active_quotation.id || depositUIState === "processing" || depositUIState === "initiated"}
                            className="px-4 py-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 text-white font-bold text-xs rounded-xl transition-all"
                          >
                            Decline Quotation
                          </button>
                          {bk.active_quotation.requires_deposit && bk.active_quotation.deposit_status !== "PAID" ? (
                            <button
                              onClick={() => openDepositModal(bk, bk.active_quotation!)}
                              disabled={respondingQuoteId === bk.active_quotation.id || depositUIState === "processing" || depositUIState === "initiated"}
                              className="px-5 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-slate-950 font-black text-xs rounded-xl transition-all shadow-sm flex items-center gap-1.5"
                            >
                              {depositUIState === "initiated" || depositUIState === "processing" ? (
                                <>
                                  <RefreshCw className="w-4 h-4 animate-spin" />
                                  <span>Processing Deposit...</span>
                                </>
                              ) : (
                                <>
                                  <CreditCard className="w-4 h-4" />
                                  <span>Pay Deposit ({bk.active_quotation.currency} {bk.active_quotation.deposit_amount}) &amp; Confirm</span>
                                </>
                              )}
                            </button>
                          ) : (
                            <button
                              onClick={() => handleAcceptQuotation(bk.active_quotation!.id)}
                              disabled={respondingQuoteId === bk.active_quotation.id}
                              className="px-5 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-black text-xs rounded-xl transition-all shadow-sm flex items-center gap-1.5"
                            >
                              <CheckCircle2 className="w-4 h-4" />
                              <span>Accept & Confirm Service</span>
                            </button>
                          )}
                        </div>
                      )}

                      {bk.active_quotation.status === "ACCEPTED" && (
                        <div className="pt-2 text-xs text-emerald-400 font-bold flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4" />
                            <span>You accepted this quotation on {bk.active_quotation.accepted_at?.split("T")[0]}.</span>
                          </div>
                          {bk.active_quotation.deposit_status === "PAID" && (
                            <span className="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2.5 py-0.5 rounded-lg text-[11px] font-mono">
                              Deposit Paid: {bk.active_quotation.currency} {bk.active_quotation.deposit_amount}
                            </span>
                          )}
                        </div>
                      )}

                      {bk.active_quotation.status === "REJECTED" && (
                        <div className="pt-2 text-xs text-rose-400 font-bold flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4" />
                          <span>
                            You declined this quotation on {bk.active_quotation.rejected_at?.split("T")[0] || "record"}.
                            {bk.active_quotation.customer_rejection_reason && ` Reason: ${bk.active_quotation.customer_rejection_reason}`}
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Service Review & Booking Actions */}
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-100">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => openChatModal(bk)}
                        className="inline-flex items-center gap-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 px-3.5 py-1.5 rounded-xl text-xs font-black transition-all shadow-xs cursor-pointer"
                      >
                        <MessageSquare className="w-3.5 h-3.5 text-indigo-600" />
                        <span>Message Workshop</span>
                      </button>

                      {bk.has_review ? (
                        <div className="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-800 border border-emerald-200 px-3 py-1 rounded-xl text-xs font-bold">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Service Reviewed</span>
                          {bk.review_rating && (
                            <span className="flex items-center text-amber-600 font-bold ml-1">
                              (★ {bk.review_rating})
                            </span>
                          )}
                        </div>
                      ) : (bk.work_order_status === "COMPLETED" || bk.is_review_eligible) ? (
                        <button
                          type="button"
                          onClick={() => openReviewModal(bk)}
                          className="inline-flex items-center gap-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 px-3.5 py-1.5 rounded-xl text-xs font-black transition-all shadow-xs cursor-pointer"
                        >
                          <Star className="w-3.5 h-3.5 fill-slate-950" />
                          <span>Rate &amp; Review Workshop</span>
                        </button>
                      ) : null}
                    </div>

                    {bk.status !== "CANCELLED" && bk.status !== "REJECTED" && (
                      <button
                        onClick={() => handleCancelBooking(bk.id)}
                        className="text-xs text-rose-600 hover:text-rose-800 font-semibold"
                      >
                        Cancel Booking Request
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: SUBMIT BOOKING REQUEST */}
      {/* ========================================================================= */}
      {bookingModalOpen && targetWorkshop && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl space-y-6 my-8 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-black uppercase tracking-wider text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                  Service Booking Request
                </span>
                <h3 className="text-lg font-black text-slate-950 mt-1">{targetWorkshop.display_name}</h3>
                <p className="text-xs text-slate-500">{targetWorkshop.city}, {targetWorkshop.country}</p>
              </div>
              <button
                onClick={() => setBookingModalOpen(false)}
                className="w-8 h-8 rounded-full bg-slate-100 text-slate-500 hover:text-slate-900 flex items-center justify-center font-bold"
              >
                ✕
              </button>
            </div>

            {bookingSuccessNumber ? (
              <div className="p-6 text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h4 className="text-lg font-black text-slate-950">Booking Request Submitted!</h4>
                <p className="text-xs text-slate-600 max-w-md mx-auto">
                  Your booking reference is <strong className="text-slate-900 font-mono">{bookingSuccessNumber}</strong>. The workshop has been notified and will review your appointment request and prepare a quotation.
                </p>
                <div className="pt-2 flex justify-center gap-3">
                  <button
                    onClick={() => {
                      setBookingModalOpen(false);
                      setActiveTab("my_bookings");
                    }}
                    className="px-5 py-2.5 bg-slate-950 text-white font-bold text-xs rounded-xl"
                  >
                    View My Bookings
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateBooking} className="space-y-4">
                {bookingError && (
                  <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs font-bold flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                    <span>{bookingError}</span>
                  </div>
                )}

                {/* 1. Vehicle Selection */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-900 block flex items-center justify-between">
                    <span>Select Vehicle from My Garage</span>
                    {onNavigateToGarage && (
                      <button
                        type="button"
                        onClick={onNavigateToGarage}
                        className="text-[11px] text-amber-600 hover:underline font-bold"
                      >
                        + Add new vehicle in Garage
                      </button>
                    )}
                  </label>
                  {vehicles.length === 0 ? (
                    <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl text-xs">
                      No vehicles found in your garage. Please register a vehicle in My Garage before booking workshop services.
                    </div>
                  ) : (
                    <select
                      value={selectedVehicleId}
                      onChange={(e) => setSelectedVehicleId(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    >
                      {vehicles.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.make} {v.model} ({v.year || "N/A"}) — {v.registration_plate || "No Plate"}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {/* 2. Select Services */}
                {targetWorkshop.services && targetWorkshop.services.length > 0 && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-900 block">Select Required Services (Optional)</label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-40 overflow-y-auto p-1">
                      {targetWorkshop.services.map((srv) => {
                        const checked = selectedServiceIds.includes(srv.id);
                        return (
                          <div
                            key={srv.id}
                            onClick={() => handleToggleService(srv.id)}
                            className={`p-3 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between ${
                              checked
                                ? "bg-purple-50 border-purple-400 text-purple-950 font-bold"
                                : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                            }`}
                          >
                            <span className="truncate pr-2">{srv.name}</span>
                            <span className="text-slate-900 shrink-0 font-bold">
                              {srv.currency} {srv.base_price}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 3. Preferred Date & Time */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-slate-900 block">Preferred Date</label>
                    <input
                      type="date"
                      min={new Date().toISOString().split("T")[0]}
                      value={preferredDate}
                      onChange={(e) => setPreferredDate(e.target.value)}
                      required
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-bold text-slate-900 block">Preferred Time Slot</label>
                    <select
                      value={preferredTimeSlot}
                      onChange={(e) => setPreferredTimeSlot(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    >
                      <option value="08:00 - 10:00">Early Morning (08:00 - 10:00)</option>
                      <option value="10:00 - 12:00">Late Morning (10:00 - 12:00)</option>
                      <option value="12:00 - 14:00">Early Afternoon (12:00 - 14:00)</option>
                      <option value="14:00 - 17:00">Late Afternoon (14:00 - 17:00)</option>
                    </select>
                  </div>
                </div>

                {/* 4. Customer Fault Notes */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-900 block">
                    Symptoms or Fault Descriptions (Optional)
                  </label>
                  <textarea
                    rows={2}
                    value={reportedFaults}
                    onChange={(e) => setReportedFaults(e.target.value)}
                    placeholder="Describe any unusual noises, warning lights, vibrations, or leaks..."
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-900 block">Additional Notes / Instructions</label>
                  <textarea
                    rows={2}
                    value={customerNotes}
                    onChange={(e) => setCustomerNotes(e.target.value)}
                    placeholder="E.g., Please check rear tyres while vehicle is on ramp..."
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>

                {/* Submit Buttons */}
                <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setBookingModalOpen(false)}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingBooking || vehicles.length === 0}
                    className="px-6 py-2.5 bg-slate-950 hover:bg-slate-900 disabled:opacity-50 text-white font-black text-xs rounded-xl transition-all shadow-sm flex items-center gap-2"
                  >
                    {submittingBooking && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                    <span>Submit Booking Request</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: DECLINE QUOTATION REASON */}
      {/* ========================================================================= */}
      {rejectReasonModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4 border border-slate-200">
            <h3 className="text-base font-black text-slate-950">Decline Quotation</h3>
            <p className="text-xs text-slate-600">
              Please share why this quotation was declined so the workshop can provide an adjusted estimate if desired.
            </p>
            <textarea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="E.g., Labour cost higher than expected, prefer aftermarket parts instead of OEM..."
              className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setRejectReasonModal(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
              >
                Go Back
              </button>
              <button
                onClick={handleRejectQuotation}
                disabled={respondingQuoteId !== null}
                className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-xl"
              >
                Confirm Decline
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: REVIEW CHANGE ORDER */}
      {/* ========================================================================= */}
      {activeChangeOrderModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4 border border-slate-200">
            <h3 className="text-base font-black text-slate-950">
              Review Additional Work Authorization (Change Order #{activeChangeOrderModal.change_order_number})
            </h3>
            <p className="text-xs text-slate-600">
              <strong>Diagnosis / Reason:</strong> {activeChangeOrderModal.reason}
            </p>
            <div className="bg-amber-50 rounded-xl p-3 border border-amber-200 text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-600">Additional Cost:</span>
                <span className="font-bold text-slate-900">
                  +{activeChangeOrderModal.currency} {parseFloat(activeChangeOrderModal.additional_amount).toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between font-bold">
                <span className="text-slate-900">Revised Authorized Total:</span>
                <span className="text-purple-700">
                  {activeChangeOrderModal.currency} {parseFloat(activeChangeOrderModal.revised_authorized_total).toFixed(2)}
                </span>
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-bold text-slate-900 block">Approval Notes (Optional)</label>
              <textarea
                rows={2}
                value={coApprovalNotes}
                onChange={(e) => setCoApprovalNotes(e.target.value)}
                placeholder="E.g., Approved with OEM parts..."
                className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setActiveChangeOrderModal(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => setCoRejectReasonModal(activeChangeOrderModal.id)}
                className="px-4 py-2 bg-rose-50 text-rose-700 hover:bg-rose-100 font-bold text-xs rounded-xl"
              >
                Decline
              </button>
              <button
                type="button"
                onClick={() => handleApproveChangeOrder(activeChangeOrderModal.id)}
                disabled={coActionLoading}
                className="px-5 py-2 bg-slate-950 hover:bg-slate-900 text-white font-bold text-xs rounded-xl flex items-center gap-2"
              >
                {coActionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Authorize & Approve</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: DECLINE CHANGE ORDER */}
      {/* ========================================================================= */}
      {coRejectReasonModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4 border border-slate-200">
            <h3 className="text-base font-black text-slate-950">Decline Additional Work</h3>
            <p className="text-xs text-slate-600">
              Please provide a reason for declining this additional repair authorization:
            </p>
            <textarea
              rows={3}
              value={coRejectReason}
              onChange={(e) => setCoRejectReason(e.target.value)}
              placeholder="E.g., Prefer to defer this repair or get alternative parts..."
              className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setCoRejectReasonModal(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRejectChangeOrder}
                disabled={coActionLoading}
                className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-xl"
              >
                Confirm Decline
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: SUBMIT WORKSHOP REVIEW */}
      {/* ========================================================================= */}
      {reviewModalOpen && targetBookingForReview && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-5 border border-slate-200 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-black uppercase tracking-wider mb-1.5 border border-emerald-200">
                  <Shield className="w-3 h-3 text-emerald-600" />
                  Verified Service Review
                </div>
                <h3 className="text-lg font-black text-slate-950">
                  Rate & Review {targetBookingForReview.workshop_name}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Booking #{targetBookingForReview.booking_reference || targetBookingForReview.booking_number} &bull; {targetBookingForReview.service_items?.[0]?.service_name || "Vehicle Service"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReviewModalOpen(false)}
                className="p-1.5 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {reviewSuccess ? (
              <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-bold flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                <span>{reviewSuccess}</span>
              </div>
            ) : (
              <form onSubmit={handleSubmitReview} className="space-y-4">
                {reviewError && (
                  <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                    <span>{reviewError}</span>
                  </div>
                )}

                {/* Primary Overall Star Rating */}
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 text-center space-y-2">
                  <label className="text-xs font-black text-slate-900 block uppercase tracking-wider">
                    Overall Experience
                  </label>
                  <div className="flex items-center justify-center gap-2">
                    {[1, 2, 3, 4, 5].map((star) => {
                      const isActive = (reviewHoverRating || reviewRating) >= star;
                      return (
                        <button
                          key={star}
                          type="button"
                          onMouseEnter={() => setReviewHoverRating(star)}
                          onMouseLeave={() => setReviewHoverRating(0)}
                          onClick={() => setReviewRating(star)}
                          className="p-1 transition-transform hover:scale-110 focus:outline-none"
                          aria-label={`Rate ${star} stars`}
                        >
                          <Star
                            className={`w-8 h-8 ${
                              isActive
                                ? "text-amber-400 fill-amber-400 drop-shadow-sm"
                                : "text-slate-300 hover:text-slate-400"
                            }`}
                          />
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-xs font-bold text-slate-700">
                    {reviewRating === 5 && "Exceptional (5 / 5)"}
                    {reviewRating === 4 && "Very Good (4 / 5)"}
                    {reviewRating === 3 && "Good (3 / 5)"}
                    {reviewRating === 2 && "Fair (2 / 5)"}
                    {reviewRating === 1 && "Poor (1 / 5)"}
                  </p>
                </div>

                {/* Dimensional Sub-ratings */}
                <div className="space-y-2.5 pt-1">
                  <p className="text-[11px] font-black uppercase tracking-wider text-slate-500">
                    Service Dimensions (Optional)
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {/* Communication */}
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1 text-center">
                      <span className="text-[11px] font-bold text-slate-700 block">Communication</span>
                      <div className="flex justify-center gap-0.5">
                        {[1, 2, 3, 4, 5].map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setReviewCommRating(s)}
                            className="p-0.5"
                          >
                            <Star
                              className={`w-4 h-4 ${
                                reviewCommRating >= s
                                  ? "text-amber-400 fill-amber-400"
                                  : "text-slate-300"
                              }`}
                            />
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Workmanship */}
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1 text-center">
                      <span className="text-[11px] font-bold text-slate-700 block">Workmanship</span>
                      <div className="flex justify-center gap-0.5">
                        {[1, 2, 3, 4, 5].map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setReviewWorkRating(s)}
                            className="p-0.5"
                          >
                            <Star
                              className={`w-4 h-4 ${
                                reviewWorkRating >= s
                                  ? "text-amber-400 fill-amber-400"
                                  : "text-slate-300"
                              }`}
                            />
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Pricing Transparency */}
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1 text-center">
                      <span className="text-[11px] font-bold text-slate-700 block">Pricing Transparency</span>
                      <div className="flex justify-center gap-0.5">
                        {[1, 2, 3, 4, 5].map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setReviewPriceRating(s)}
                            className="p-0.5"
                          >
                            <Star
                              className={`w-4 h-4 ${
                                reviewPriceRating >= s
                                  ? "text-amber-400 fill-amber-400"
                                  : "text-slate-300"
                              }`}
                            />
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Review Title */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-900 block">
                    Headline / Summary (Optional)
                  </label>
                  <input
                    type="text"
                    value={reviewTitle}
                    onChange={(e) => setReviewTitle(e.target.value)}
                    placeholder="E.g., Prompt diagnosis, transparent pricing and polite team"
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    maxLength={120}
                  />
                </div>

                {/* Review Comment */}
                <div className="space-y-1">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-bold text-slate-900">
                      Your Detailed Experience <span className="text-rose-500">*</span>
                    </label>
                    <span className="text-[10px] text-slate-500">Min 5 characters</span>
                  </div>
                  <textarea
                    rows={4}
                    value={reviewComment}
                    onChange={(e) => setReviewComment(e.target.value)}
                    placeholder="Describe how the workshop handled your vehicle, turnaround time, communication, and overall quality of work..."
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    required
                  />
                </div>

                <div className="flex items-center justify-between pt-2">
                  <button
                    type="button"
                    onClick={() => setReviewModalOpen(false)}
                    className="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingReview || reviewComment.trim().length < 5}
                    className="px-6 py-2.5 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black text-xs rounded-xl flex items-center gap-2 shadow-sm disabled:opacity-50"
                  >
                    {submittingReview && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                    <span>Publish Review</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* DRAWER / MODAL: WORKSHOP REVIEWS & REPUTATION */}
      {/* ========================================================================= */}
      {reviewsDrawerOpen && selectedWorkshopForReviews && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl space-y-6 border border-slate-200 max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-black text-slate-950">
                    {selectedWorkshopForReviews.business_name || selectedWorkshopForReviews.display_name}
                  </h3>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                    <Shield className="w-3 h-3 text-emerald-600" />
                    Verified Reviews
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-slate-400" />
                  {selectedWorkshopForReviews.city}, {selectedWorkshopForReviews.postal_code}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReviewsDrawerOpen(false)}
                className="p-1.5 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Reputation Summary Card */}
            {workshopReputation && (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 grid grid-cols-1 sm:grid-cols-3 gap-4 items-center">
                {/* Score & Stars */}
                <div className="text-center sm:border-r border-slate-200 sm:pr-4 space-y-1">
                  <div className="text-4xl font-black text-slate-950">
                    {workshopReputation.average_rating ? workshopReputation.average_rating.toFixed(1) : "—"}
                  </div>
                  <div className="flex justify-center items-center gap-1 text-amber-400">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <Star
                        key={star}
                        className={`w-4 h-4 ${
                          (workshopReputation.average_rating || 0) >= star
                            ? "fill-amber-400 text-amber-400"
                            : "text-slate-300"
                        }`}
                      />
                    ))}
                  </div>
                  <div className="text-xs text-slate-500 font-bold">
                    {workshopReputation.total_reviews} verified {workshopReputation.total_reviews === 1 ? "review" : "reviews"}
                  </div>
                </div>

                {/* Star Distribution Breakdown */}
                <div className="space-y-1.5 sm:col-span-2">
                  {[5, 4, 3, 2, 1].map((s) => {
                    const count = workshopReputation.distribution[String(s)] || 0;
                    const percent = workshopReputation.total_reviews > 0
                      ? Math.round((count / workshopReputation.total_reviews) * 100)
                      : 0;
                    return (
                      <div key={s} className="flex items-center gap-2 text-xs">
                        <span className="w-8 font-bold text-slate-600 flex items-center gap-0.5 justify-end">
                          {s} <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                        </span>
                        <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-amber-400 rounded-full transition-all"
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                        <span className="w-8 text-[11px] text-slate-500 text-right">{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Dimensional Sub-scores if present */}
            {workshopReputation?.sub_ratings && (
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Communication</span>
                  <span className="text-sm font-black text-slate-900">
                    {workshopReputation.sub_ratings.communication ? `${workshopReputation.sub_ratings.communication.toFixed(1)} / 5` : "—"}
                  </span>
                </div>
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Workmanship</span>
                  <span className="text-sm font-black text-slate-900">
                    {workshopReputation.sub_ratings.workmanship ? `${workshopReputation.sub_ratings.workmanship.toFixed(1)} / 5` : "—"}
                  </span>
                </div>
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Pricing</span>
                  <span className="text-sm font-black text-slate-900">
                    {workshopReputation.sub_ratings.pricing_transparency ? `${workshopReputation.sub_ratings.pricing_transparency.toFixed(1)} / 5` : "—"}
                  </span>
                </div>
              </div>
            )}

            {/* Review List Section */}
            <div className="space-y-4">
              <h4 className="text-xs font-black uppercase tracking-wider text-slate-500">
                Customer Feedback ({workshopReviewsList.length})
              </h4>

              {loadingWorkshopReviews && (
                <div className="py-12 text-center text-slate-500 text-xs flex items-center justify-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin text-amber-500" />
                  <span>Loading verified reviews...</span>
                </div>
              )}

              {workshopReviewsError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs font-bold flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                  <span>{workshopReviewsError}</span>
                </div>
              )}

              {!loadingWorkshopReviews && !workshopReviewsError && workshopReviewsList.length === 0 && (
                <div className="py-12 text-center rounded-2xl bg-slate-50 border border-dashed border-slate-200 space-y-2">
                  <Star className="w-8 h-8 text-slate-300 mx-auto" />
                  <p className="text-xs font-bold text-slate-600">No customer reviews yet</p>
                  <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                    Reviews can only be submitted by verified customers who booked and completed work with this workshop on DriverXtra.
                  </p>
                </div>
              )}

              {!loadingWorkshopReviews && workshopReviewsList.map((review) => (
                <div
                  key={review.id}
                  className="p-4 rounded-2xl border border-slate-200 bg-white shadow-sm space-y-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <div className="flex text-amber-400">
                          {[1, 2, 3, 4, 5].map((star) => (
                            <Star
                              key={star}
                              className={`w-3.5 h-3.5 ${
                                review.rating >= star
                                  ? "fill-amber-400 text-amber-400"
                                  : "text-slate-300"
                              }`}
                            />
                          ))}
                        </div>
                        {review.title && (
                          <h5 className="text-xs font-black text-slate-900">{review.title}</h5>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-slate-500">
                        <span className="font-bold text-slate-700">{review.buyer_name}</span>
                        <span>&bull;</span>
                        <span>{new Date(review.created_at).toLocaleDateString()}</span>
                        {review.vehicle_display && (
                          <>
                            <span>&bull;</span>
                            <span className="px-2 py-0.5 rounded bg-slate-100 font-mono text-[10px] text-slate-700 font-bold">
                              {review.vehicle_display}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    {review.is_verified_service && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200 shrink-0">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        Verified Service
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-line">
                    {review.comment}
                  </p>

                  {/* Dimensional breakdown badges if present */}
                  {(review.communication_rating || review.workmanship_rating || review.pricing_transparency_rating) && (
                    <div className="flex flex-wrap gap-2 pt-1 border-t border-slate-100 text-[10px] text-slate-500">
                      {review.communication_rating && (
                        <span>Communication: <strong className="text-slate-700">{review.communication_rating}/5</strong></span>
                      )}
                      {review.workmanship_rating && (
                        <span>Workmanship: <strong className="text-slate-700">{review.workmanship_rating}/5</strong></span>
                      )}
                      {review.pricing_transparency_rating && (
                        <span>Pricing: <strong className="text-slate-700">{review.pricing_transparency_rating}/5</strong></span>
                      )}
                    </div>
                  )}

                  {/* Official Workshop Response if present */}
                  {review.workshop_reply && (
                    <div className="mt-3 p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-bold text-slate-900 flex items-center gap-1.5">
                          <MessageSquare className="w-3.5 h-3.5 text-indigo-600" />
                          Official Response from {review.workshop_name}
                        </span>
                        {review.workshop_reply_at && (
                          <span className="text-[10px] text-slate-500">
                            {new Date(review.workshop_reply_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-700 leading-relaxed italic">
                        &ldquo;{review.workshop_reply}&rdquo;
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setReviewsDrawerOpen(false)}
                className="px-5 py-2.5 bg-slate-950 hover:bg-slate-900 text-white font-bold text-xs rounded-xl"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Deposit Payment Modal */}
      {depositModalOpen && targetQuotationForDeposit && targetBookingForDeposit && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-5 animate-in fade-in zoom-in duration-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-600">
                  <CreditCard className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-black text-slate-900">
                      Workshop Quotation Deposit
                    </h3>
                    {/* Explicit UI State Badges */}
                    {depositUIState === "initiated" && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1">
                        <RefreshCw className="w-2.5 h-2.5 animate-spin" /> Payment initiated
                      </span>
                    )}
                    {depositUIState === "processing" && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1">
                        <RefreshCw className="w-2.5 h-2.5 animate-spin" /> Processing
                      </span>
                    )}
                    {depositUIState === "paid_and_verified" && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                        <CheckCircle2 className="w-2.5 h-2.5" /> Paid and verified
                      </span>
                    )}
                    {depositUIState === "failed" && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1">
                        <AlertCircle className="w-2.5 h-2.5" /> Payment failed
                      </span>
                    )}
                    {depositUIState === "cancelled" && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300 flex items-center gap-1">
                        <AlertTriangle className="w-2.5 h-2.5" /> Payment cancelled
                      </span>
                    )}
                    {depositUIState === "required" && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1">
                        <Lock className="w-2.5 h-2.5" /> Payment required
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">
                    Booking: {targetBookingForDeposit.booking_number} • Quote: #{targetQuotationForDeposit.quotation_number}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (depositUIState !== "processing") {
                    setDepositModalOpen(false);
                    setDepositUIState("required");
                    setDepositError(null);
                    setDepositSuccess(null);
                  }
                }}
                disabled={depositUIState === "processing"}
                className="p-2 text-slate-400 hover:text-slate-600 rounded-xl hover:bg-slate-100 disabled:opacity-30 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body: State-specific renderings */}
            {depositUIState === "paid_and_verified" ? (
              <div className="py-6 text-center space-y-4">
                <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <div>
                  <h4 className="text-base font-black text-slate-900">Deposit Paid &amp; Verified!</h4>
                  <p className="text-xs text-slate-600 max-w-sm mx-auto mt-1">
                    {depositSuccess || `Your quotation has been accepted and your workshop appointment is confirmed. Work Order has been generated for ${targetBookingForDeposit.workshop_name}.`}
                  </p>
                </div>
                <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200 max-w-xs mx-auto text-xs text-emerald-900 font-mono">
                  Amount Paid: {targetQuotationForDeposit.currency} {targetQuotationForDeposit.deposit_amount}
                </div>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setDepositModalOpen(false);
                      setDepositUIState("required");
                    }}
                    className="px-6 py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl"
                  >
                    Done • View Booking
                  </button>
                </div>
              </div>
            ) : depositUIState === "processing" ? (
              <div className="py-10 text-center space-y-3">
                <RefreshCw className="w-9 h-9 animate-spin mx-auto text-amber-500" />
                <div>
                  <h4 className="text-sm font-black text-slate-900">Processing &amp; Verifying Payment...</h4>
                  <p className="text-xs text-slate-500 mt-1">
                    Authoritatively validating cryptographic payment signature and confirming booking with the server.
                  </p>
                </div>
                <p className="text-[11px] text-amber-700 bg-amber-50 rounded-lg p-2 max-w-sm mx-auto font-medium">
                  Please do not close or reload this page while verification completes.
                </p>
              </div>
            ) : depositUIState === "failed" ? (
              <div className="space-y-4">
                <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5">
                  <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block text-sm">Payment Verification Failed</span>
                    <span className="mt-0.5 block">{depositError || "Payment could not be verified by the gateway or was declined."}</span>
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setDepositModalOpen(false);
                      setDepositUIState("required");
                    }}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    onClick={() => openDepositModal(targetBookingForDeposit, targetQuotationForDeposit)}
                    className="px-5 py-2 bg-amber-500 hover:bg-amber-600 text-slate-950 font-black text-xs rounded-xl"
                  >
                    Retry Payment
                  </button>
                </div>
              </div>
            ) : depositUIState === "cancelled" ? (
              <div className="space-y-4">
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-slate-800 text-xs flex items-start gap-2.5">
                  <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block text-sm">Payment Checkout Cancelled</span>
                    <span className="mt-0.5 block">{depositError || "Checkout was cancelled or dismissed. Your quotation remains pending deposit and can be resumed at any time."}</span>
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setDepositModalOpen(false);
                      setDepositUIState("required");
                    }}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    onClick={() => openDepositModal(targetBookingForDeposit, targetQuotationForDeposit)}
                    className="px-5 py-2 bg-amber-500 hover:bg-amber-600 text-slate-950 font-black text-xs rounded-xl"
                  >
                    Resume Payment
                  </button>
                </div>
              </div>
            ) : depositLoading ? (
              <div className="py-12 text-center space-y-3">
                <RefreshCw className="w-8 h-8 animate-spin mx-auto text-amber-500" />
                <p className="text-sm font-bold text-slate-600">
                  Connecting to secure payment gateway...
                </p>
                <p className="text-xs text-slate-400">
                  Initializing order session and cryptographic token
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Financial Breakdown Card */}
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 space-y-2.5">
                  <div className="flex justify-between text-xs text-slate-600">
                    <span>Workshop Partner:</span>
                    <span className="font-bold text-slate-900">{targetBookingForDeposit.workshop_name}</span>
                  </div>
                  <div className="flex justify-between text-xs text-slate-600">
                    <span>Total Service Quotation:</span>
                    <span className="font-medium">
                      {targetQuotationForDeposit.currency} {targetQuotationForDeposit.total_amount}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-amber-700 font-bold pt-1 border-t border-slate-200">
                    <span>Required Upfront Deposit ({targetQuotationForDeposit.deposit_percentage}%):</span>
                    <span className="text-sm font-black text-amber-600">
                      {targetQuotationForDeposit.currency} {targetQuotationForDeposit.deposit_amount}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-slate-500">
                    <span>Balance Due Upon Completion:</span>
                    <span>
                      {targetQuotationForDeposit.currency}{" "}
                      {(
                        parseFloat(targetQuotationForDeposit.total_amount) -
                        parseFloat(targetQuotationForDeposit.deposit_amount || "0")
                      ).toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Gateway Provider & Security Notice */}
                <div className="p-3 bg-slate-100 rounded-xl space-y-1.5 text-xs text-slate-600">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-bold text-slate-800">
                      <Lock className="w-3.5 h-3.5 text-emerald-600" />
                      Payment Gateway:
                    </span>
                    <span className="font-mono text-[11px] font-bold text-slate-700 uppercase">
                      {depositSession?.payment_session?.provider || targetQuotationForDeposit.deposit_provider || (targetQuotationForDeposit.currency === "GBP" ? "STRIPE" : "RAZORPAY")}
                    </span>
                  </div>
                  {depositSession?.payment_session?.provider_order_id && (
                    <div className="text-[11px] font-mono text-slate-500 truncate">
                      Gateway Order: {depositSession.payment_session.provider_order_id}
                    </div>
                  )}
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-500 pt-1 border-t border-slate-200">
                    <Shield className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                    <span>Authoritative HMAC cryptographic signature verification guarantees anti-tamper security.</span>
                  </div>
                </div>

                {/* Guidance notice */}
                <p className="text-xs text-slate-500 text-center">
                  {(depositSession?.payment_session?.provider || (targetQuotationForDeposit.currency === "GBP" ? "STRIPE" : "RAZORPAY")).toUpperCase() === "STRIPE"
                    ? "Click below to confirm your deposit via Stripe UK test gateway."
                    : "Click below to open the secure Razorpay Checkout window and complete your deposit."}
                </p>

                {/* Actions */}
                <div className="flex justify-end items-center gap-2.5 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => {
                      setDepositModalOpen(false);
                      setDepositUIState("required");
                    }}
                    className="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmDepositPayment}
                    className="px-6 py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-slate-950 font-black text-xs rounded-xl transition-all shadow-md flex items-center gap-2"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>
                      Confirm &amp; Pay Deposit ({targetQuotationForDeposit.currency}{" "}
                      {targetQuotationForDeposit.deposit_amount})
                    </span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      {/* ========================================================================= */}
      {/* MODAL: WORKSHOP MESSAGING / REAL-TIME CHAT */}
      {/* ========================================================================= */}
      {chatModalOpen && targetBookingForChat && (
        <WorkshopChatModal
          booking={targetBookingForChat}
          onClose={() => {
            setChatModalOpen(false);
            setTargetBookingForChat(null);
          }}
          currentUserId={user?.id}
        />
      )}
    </div>
  );
}

