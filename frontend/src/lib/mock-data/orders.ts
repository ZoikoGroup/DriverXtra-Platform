// Canonical Commerce & Escrow Data Model Grounded in Doc 09 & Doc 10

export type OrderState =
  | "PENDING_CONFIRMATION"
  | "CONFIRMED"
  | "PROCESSING"
  | "FULFILLING"
  | "COMPLETED"
  | "CANCELLED";

export type EscrowState =
  | "HELD_IN_CUSTODY"
  | "RELEASE_ELIGIBLE"
  | "DISBURSED"
  | "REFUNDED"
  | "DISPUTE_LOCKED";

export interface OrderLineItem {
  id: string;
  itemType: "VEHICLE" | "PART" | "SERVICE";
  title: string;
  unitPrice: number;
  quantity: number;
  sellerName: string;
  guaranteedFitmentVerified?: boolean;
}

export interface PlatformOrder {
  id: string;              // Order reference formatted as per Doc 09
  placedAt: string;
  buyerId: string;
  buyerName: string;
  orderState: OrderState;
  escrowState: EscrowState;
  totalMinorAmount: number;   // In cents/pence
  currency: string;
  items: OrderLineItem[];
  handoverAuthToken: string;  // Cryptographic token for physical vehicle handover
  shippingCarrier?: string;
  trackingNumber?: string;
  escrowReleaseConditions: string;
}

export const MOCK_ORDERS: PlatformOrder[] = [
  {
    id: "DX-ORD-2026-98421",
    placedAt: "2026-10-12T14:32:00Z",
    buyerId: "usr_01j7x9p2k0001",
    buyerName: "Mark Harrison",
    orderState: "CONFIRMED",
    escrowState: "HELD_IN_CUSTODY",
    totalMinorAmount: 50000, // £500.00 reservation deposit
    currency: "GBP",
    items: [
      {
        id: "line_001",
        itemType: "VEHICLE",
        title: "2024 Mercedes-Benz C 300 AMG Line Premium",
        unitPrice: 500,
        quantity: 1,
        sellerName: "Apex Automotive Group UK"
      }
    ],
    handoverAuthToken: "DX-HANDOVER-9842-8812-4401",
    escrowReleaseConditions: "Funds release triggered upon physical collection scan or buyer electronic sign-off."
  },
  {
    id: "DX-ORD-2026-91024",
    placedAt: "2026-10-09T09:15:00Z",
    buyerId: "usr_01j7x9p2k0001",
    buyerName: "Mark Harrison",
    orderState: "FULFILLING",
    escrowState: "HELD_IN_CUSTODY",
    totalMinorAmount: 21500, // £215.00
    currency: "GBP",
    items: [
      {
        id: "line_002",
        itemType: "PART",
        title: "Brembo Prime Two-Piece Front Brake Disc Rotor Set (348mm)",
        unitPrice: 215,
        quantity: 1,
        sellerName: "AutoBavarian Parts Ltd",
        guaranteedFitmentVerified: true
      }
    ],
    handoverAuthToken: "DX-DELIVERY-TOKEN-091024",
    shippingCarrier: "DPD Express Guaranteed",
    trackingNumber: "DPD-UK-982194012",
    escrowReleaseConditions: "Escrow funds released to supplier 48 hours after carrier delivery scan."
  },
  {
    id: "DX-ORD-2026-88120",
    placedAt: "2026-09-28T11:00:00Z",
    buyerId: "usr_01j7x9p2k0001",
    buyerName: "Mark Harrison",
    orderState: "COMPLETED",
    escrowState: "DISBURSED",
    totalMinorAmount: 28900, // £289.00
    currency: "GBP",
    items: [
      {
        id: "line_003",
        itemType: "SERVICE",
        title: "Major Scheduled Service & Brake Fluid Flush",
        unitPrice: 289,
        quantity: 1,
        sellerName: "Apex Bavarian Performance & MOT Centre"
      }
    ],
    handoverAuthToken: "DX-SERVICE-COMPLETED-88120",
    escrowReleaseConditions: "Work order sign-off completed and written to Vehicle Master."
  }
];
