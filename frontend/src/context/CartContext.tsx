"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { api, ApiError } from "@/lib/api/client";

const CART_STORAGE_KEY = "dx_shopping_cart_v1";

export interface CartItem {
  listing_id: string; // Unique UUID of the SparePartListing or VehicleListing
  listing_type: "part" | "vehicle";
  title: string;
  brand: string;
  mpn?: string;
  image_url?: string | null;
  condition: string;
  price: number; // Unit price
  currency: string;
  gst_rate?: number;
  stock_quantity: number; // Last known stock quantity from backend (1 for unique vehicle)
  quantity: number; // Quantity selected by buyer (strictly 1 for vehicle)
  seller_id: string;
  seller_name: string;
  organisation_name?: string | null;
}

export interface SellerCartGroup {
  sellerKey: string;
  sellerName: string;
  organisationName?: string | null;
  items: CartItem[];
  subtotal: number;
  totalUnits: number;
}

export interface CartValidationResult {
  isValid: boolean;
  issues: string[];
  calculatedSummary?: {
    subtotal_taxable_amount: string;
    cgst_amount: string;
    sgst_amount: string;
    igst_amount: string;
    total_tax_amount: string;
    total_amount: string;
    currency: string;
  } | null;
}

export interface ValidateInventoryOptions {
  country?: string;
  currency?: string;
  place_of_supply?: string;
}

interface CartContextType {
  items: CartItem[];
  totalUnits: number;
  distinctItemCount: number;
  displayedSubtotal: number;
  currency: string;
  groupedBySeller: SellerCartGroup[];
  isCartOpen: boolean;
  openCart: () => void;
  closeCart: () => void;
  toggleCart: () => void;
  addItem: (
    item: Omit<CartItem, "quantity">,
    quantityToAdd?: number
  ) => { success: boolean; message: string };
  removeItem: (listingId: string) => void;
  updateQuantity: (
    listingId: string,
    newQuantity: number
  ) => { success: boolean; message: string };
  clearCart: () => void;
  isItemInCart: (listingId: string) => boolean;
  getItemQuantity: (listingId: string) => number;
  validateInventory: (options?: ValidateInventoryOptions) => Promise<CartValidationResult>;
  isValidating: boolean;
  lastValidationResult: CartValidationResult | null;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

function sanitizeCartItem(raw: unknown): CartItem | null {
  if (!raw || typeof raw !== "object") return null;
  const candidate = raw as Record<string, unknown>;

  if (typeof candidate.listing_id !== "string" || !candidate.listing_id.trim()) {
    return null;
  }

  const quantity = Number(candidate.quantity);
  const price = Number(candidate.price);
  const stock_quantity = Number(candidate.stock_quantity);

  if (Number.isNaN(quantity) || quantity <= 0) return null;
  if (Number.isNaN(price) || price < 0) return null;
  if (Number.isNaN(stock_quantity) || stock_quantity < 0) return null;

  const isVehicle = candidate.listing_type === "vehicle";
  const listing_type: "part" | "vehicle" = isVehicle ? "vehicle" : "part";
  const effectiveStock = isVehicle ? 1 : stock_quantity;
  const effectiveQty = isVehicle ? 1 : Math.min(quantity, Math.max(1, stock_quantity));

  return {
    listing_id: candidate.listing_id.trim(),
    listing_type,
    title:
      typeof candidate.title === "string"
        ? candidate.title
        : isVehicle
        ? "Marketplace Vehicle"
        : "Spare Part",
    brand: typeof candidate.brand === "string" ? candidate.brand : "Generic",
    mpn: typeof candidate.mpn === "string" ? candidate.mpn : undefined,
    image_url:
      typeof candidate.image_url === "string" ? candidate.image_url : null,
    condition:
      typeof candidate.condition === "string" ? candidate.condition : "VERY_GOOD",
    price: price,
    currency:
      typeof candidate.currency === "string"
        ? candidate.currency
        : isVehicle
        ? "GBP"
        : "INR",
    gst_rate:
      typeof candidate.gst_rate === "number"
        ? candidate.gst_rate
        : candidate.gst_rate
        ? Number(candidate.gst_rate)
        : undefined,
    stock_quantity: effectiveStock,
    quantity: effectiveQty,
    seller_id:
      typeof candidate.seller_id === "string"
        ? candidate.seller_id
        : "unknown-seller",
    seller_name:
      typeof candidate.seller_name === "string"
        ? candidate.seller_name
        : "Verified Seller",
    organisation_name:
      typeof candidate.organisation_name === "string"
        ? candidate.organisation_name
        : null,
  };
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [lastValidationResult, setLastValidationResult] =
    useState<CartValidationResult | null>(null);

  // Safely restore cart from localStorage after mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(CART_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          const validItems: CartItem[] = [];
          for (const raw of parsed) {
            const clean = sanitizeCartItem(raw);
            if (clean) validItems.push(clean);
          }
          setItems(validItems);
        }
      }
    } catch (err) {
      console.warn("[Cart] Unable to restore cart from localStorage:", err);
      // Fallback to empty cart on parse error without disrupting the app
      setItems([]);
    } finally {
      setIsInitialized(true);
    }
  }, []);

  // Persist cart whenever items change (skip during initial mount)
  useEffect(() => {
    if (!isInitialized) return;
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
    } catch (err) {
      console.warn("[Cart] Unable to persist cart to localStorage:", err);
    }
  }, [items, isInitialized]);

  const openCart = useCallback(() => setIsCartOpen(true), []);
  const closeCart = useCallback(() => setIsCartOpen(false), []);
  const toggleCart = useCallback(() => setIsCartOpen((prev) => !prev), []);

  const isItemInCart = useCallback(
    (listingId: string) => items.some((i) => i.listing_id === listingId),
    [items]
  );

  const getItemQuantity = useCallback(
    (listingId: string) => {
      const found = items.find((i) => i.listing_id === listingId);
      return found ? found.quantity : 0;
    },
    [items]
  );

  const addItem = useCallback(
    (item: Omit<CartItem, "quantity">, quantityToAdd = 1) => {
      if (quantityToAdd <= 0) {
        return { success: false, message: "Quantity must be greater than zero." };
      }

      if (item.stock_quantity <= 0) {
        return {
          success: false,
          message: `"${item.title}" is out of stock and cannot be added.`,
        };
      }

      let resultMessage = "";
      let success = true;

      setItems((prev) => {
        const existingIndex = prev.findIndex(
          (i) => i.listing_id === item.listing_id
        );

        // Vehicle uniqueness check: Vehicles represent single physical assets
        if (item.listing_type === "vehicle") {
          if (existingIndex >= 0) {
            success = false;
            resultMessage = `"${item.title}" is already in your basket. Each vehicle is a unique asset (quantity cannot exceed 1).`;
            return prev;
          }
          resultMessage = `Added vehicle "${item.title}" to your shopping basket.`;
          return [...prev, { ...item, quantity: 1, stock_quantity: 1 }];
        }

        if (existingIndex >= 0) {
          const existing = prev[existingIndex];
          const proposedQty = existing.quantity + quantityToAdd;

          if (proposedQty > item.stock_quantity) {
            const availableToAdd = item.stock_quantity - existing.quantity;
            if (availableToAdd <= 0) {
              success = false;
              resultMessage = `Maximum available stock (${item.stock_quantity}) for "${item.title}" is already in your cart.`;
              return prev;
            }
            // Add remaining available units up to stock limit
            const updated = [...prev];
            updated[existingIndex] = {
              ...existing,
              ...item,
              quantity: item.stock_quantity,
            };
            resultMessage = `Added ${availableToAdd} unit(s). Cart reached maximum available stock (${item.stock_quantity}).`;
            return updated;
          }

          const updated = [...prev];
          updated[existingIndex] = {
            ...existing,
            ...item,
            quantity: proposedQty,
          };
          resultMessage = `Added ${quantityToAdd} more unit(s) of "${item.title}" to your cart.`;
          return updated;
        }

        // New item
        if (quantityToAdd > item.stock_quantity) {
          success = false;
          resultMessage = `Requested quantity (${quantityToAdd}) exceeds available stock (${item.stock_quantity}).`;
          return prev;
        }

        resultMessage = `Added "${item.title}" to your shopping cart.`;
        return [...prev, { ...item, quantity: quantityToAdd }];
      });

      // Clear any prior validation cache so user is prompted to revalidate
      setLastValidationResult(null);

      return { success, message: resultMessage };
    },
    []
  );

  const removeItem = useCallback((listingId: string) => {
    setItems((prev) => prev.filter((i) => i.listing_id !== listingId));
    setLastValidationResult(null);
  }, []);

  const updateQuantity = useCallback(
    (listingId: string, newQuantity: number) => {
      if (newQuantity <= 0) {
        removeItem(listingId);
        return { success: true, message: "Item removed from cart." };
      }

      let success = true;
      let message = "Quantity updated.";

      setItems((prev) => {
        const index = prev.findIndex((i) => i.listing_id === listingId);
        if (index === -1) {
          success = false;
          message = "Item not found in cart.";
          return prev;
        }

        const existing = prev[index];

        // Vehicle listings represent single physical assets
        if (existing.listing_type === "vehicle" && newQuantity > 1) {
          success = false;
          message = "Vehicles represent individual physical assets. Quantity cannot exceed 1.";
          return prev;
        }

        if (newQuantity > existing.stock_quantity) {
          success = false;
          message = `Cannot set quantity to ${newQuantity}. Maximum available stock is ${existing.stock_quantity}.`;
          const updated = [...prev];
          updated[index] = {
            ...existing,
            quantity: existing.stock_quantity,
          };
          return updated;
        }

        const updated = [...prev];
        updated[index] = {
          ...existing,
          quantity: newQuantity,
        };
        message = `Updated quantity to ${newQuantity}.`;
        return updated;
      });

      setLastValidationResult(null);
      return { success, message };
    },
    [removeItem]
  );

  const clearCart = useCallback(() => {
    setItems([]);
    setLastValidationResult(null);
  }, []);

  // Calculations
  const totalUnits = useMemo(
    () => items.reduce((sum, item) => sum + item.quantity, 0),
    [items]
  );

  const distinctItemCount = items.length;

  const displayedSubtotal = useMemo(
    () =>
      items.reduce((sum, item) => sum + Number(item.price) * item.quantity, 0),
    [items]
  );

  const currency = items[0]?.currency || "INR";

  // Group items by Seller / Organisation
  const groupedBySeller = useMemo(() => {
    const map = new Map<string, SellerCartGroup>();

    for (const item of items) {
      const key = item.organisation_name
        ? `org:${item.organisation_name}`
        : `seller:${item.seller_id}`;
      const sellerDisplayName =
        item.organisation_name || item.seller_name || "Verified Seller";

      const existing = map.get(key);
      const lineTotal = Number(item.price) * item.quantity;

      if (existing) {
        existing.items.push(item);
        existing.subtotal += lineTotal;
        existing.totalUnits += item.quantity;
      } else {
        map.set(key, {
          sellerKey: key,
          sellerName: sellerDisplayName,
          organisationName: item.organisation_name || null,
          items: [item],
          subtotal: lineTotal,
          totalUnits: item.quantity,
        });
      }
    }

    return Array.from(map.values());
  }, [items]);

  // Live Inventory & Price Validation against Backend
  const validateInventory = useCallback(
    async (options?: ValidateInventoryOptions): Promise<CartValidationResult> => {
      if (items.length === 0) {
        const emptyResult = { isValid: true, issues: [], calculatedSummary: null };
        setLastValidationResult(emptyResult);
        return emptyResult;
      }

      setIsValidating(true);
      const issues: string[] = [];

      // Separate spare parts and vehicle items
      const partItems = items.filter((i) => i.listing_type !== "vehicle");
      const vehicleItems = items.filter((i) => i.listing_type === "vehicle");

      if (vehicleItems.length > 0) {
        issues.push(
          "Vehicles represent individual physical assets and require title transfer, inspection, and direct seller consultation. Please use the Contact Seller enquiry flow; automated checkout is reserved for spare parts."
        );
      }

      // First pass: local stock validation check
      for (const item of items) {
        if (item.quantity > item.stock_quantity) {
          issues.push(
            `"${item.title}" quantity (${item.quantity}) exceeds available stock (${item.stock_quantity}).`
          );
        }
      }

      // If there are no spare parts to calculate, return result with vehicle enquiry advisory
      if (partItems.length === 0) {
        setIsValidating(false);
        const vehicleOnlyResult: CartValidationResult = {
          isValid: false,
          issues,
          calculatedSummary: null,
        };
        setLastValidationResult(vehicleOnlyResult);
        return vehicleOnlyResult;
      }

      try {
        const targetCountry = options?.country || "India";
        const isUK =
          targetCountry.toLowerCase().includes("kingdom") ||
          targetCountry.toLowerCase() === "uk" ||
          targetCountry.toLowerCase() === "gb";
        const targetCurrency =
          options?.currency || (isUK ? "GBP" : "INR");
        const targetSupply =
          options?.place_of_supply || (isUK ? "London" : "MH");

        // Call official backend calculation endpoint: POST /api/v1/marketplace/orders/calculate/
        const payload = {
          items: partItems.map((i) => ({
            listing_id: i.listing_id,
            quantity: i.quantity,
          })),
          currency: targetCurrency,
          shipping_country: targetCountry,
          place_of_supply: targetSupply,
        };

        const res = await api.marketplace.calculateCheckout(payload);

        const summary = {
          subtotal_taxable_amount: String(res.subtotal_taxable_amount || "0.00"),
          cgst_amount: String(res.cgst_amount || "0.00"),
          sgst_amount: String(res.sgst_amount || "0.00"),
          igst_amount: String(res.igst_amount || "0.00"),
          total_tax_amount: String(res.total_tax_amount || "0.00"),
          total_amount: String(res.total_amount || "0.00"),
          currency: String(res.currency || targetCurrency),
        };

        const result: CartValidationResult = {
          isValid: issues.length === 0,
          issues,
          calculatedSummary: summary,
        };

        setLastValidationResult(result);
        return result;
      } catch (err: unknown) {
        let errorMessage = "Unable to validate cart items. Please refresh and try again.";
        if (err instanceof ApiError) {
          errorMessage = err.message;
        } else if (err instanceof Error) {
          errorMessage = err.message;
        }

        // If user is unauthenticated, calculation endpoint returns 401
        if (err instanceof ApiError && err.code === 401) {
          // Fall back to local validation for guest buyers
          const result: CartValidationResult = {
            isValid: issues.length === 0,
            issues: [
              ...issues,
              "Please sign in to compute verified statutory taxes and place your order.",
            ],
            calculatedSummary: null,
          };
          setLastValidationResult(result);
          return result;
        }

        issues.push(errorMessage);
        const result: CartValidationResult = {
          isValid: false,
          issues,
          calculatedSummary: null,
        };
        setLastValidationResult(result);
        return result;
      } finally {
        setIsValidating(false);
      }
    },
    [items]
  );

  return (
    <CartContext.Provider
      value={{
        items,
        totalUnits,
        distinctItemCount,
        displayedSubtotal,
        currency,
        groupedBySeller,
        isCartOpen,
        openCart,
        closeCart,
        toggleCart,
        addItem,
        removeItem,
        updateQuantity,
        clearCart,
        isItemInCart,
        getItemQuantity,
        validateInventory,
        isValidating,
        lastValidationResult,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error("useCart must be used within a CartProvider");
  }
  return context;
}
