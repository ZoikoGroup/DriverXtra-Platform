import React from "react";
import {
  ShoppingBag,
  Wrench,
  Package,
  RotateCcw,
  Heart,
  MessageSquare,
  Layers,
  FileCheck2,
  Building2,
  Headphones,
  User,
  Boxes,
  ShieldCheck,
  Scale,
  ClipboardCheck,
  CheckCircle2,
  Landmark,
  UserPlus,
  LayoutDashboard,
  Store,
  Users,
  Receipt,
} from "lucide-react";
import { PrototypeUser } from "@/lib/prototype-auth/types";

export interface NavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

export const BUYER_NAV_ITEMS: NavItem[] = [
  { id: "marketplace_browse", label: "Marketplace (Vehicles & Parts)", icon: ShoppingBag, badge: "Browse" },
  { id: "workshops_browse", label: "Workshops & Bookings", icon: Wrench, badge: "Book" },
  { id: "my_orders", label: "My Orders", icon: Package, badge: "Purchases" },
  { id: "buyer_returns_refunds", label: "My Returns & Refunds", icon: RotateCcw, badge: "Returns" },
  { id: "favourites", label: "Saved Items", icon: Heart, badge: "Saved" },
  { id: "my_enquiries", label: "My Enquiries", icon: MessageSquare, badge: "Direct" },
  { id: "garage", label: "My Garage", icon: Layers, badge: "Vehicles" },
  { id: "seller_onboarding", label: "Apply to sell / Apply as workshop", icon: FileCheck2, badge: "Apply" },
  { id: "organisations", label: "Organisations & Teams", icon: Building2 },
  { id: "my_tickets", label: "Help & Support", icon: Headphones, badge: "Help" },
  { id: "profile", label: "My Profile", icon: User },
];

export const SELLER_NAV_ITEMS: NavItem[] = [
  { id: "seller_inventory", label: "My Inventory (Vehicles & Parts)", icon: Layers, badge: "Manage" },
  { id: "seller_orders", label: "Customer Orders", icon: Boxes, badge: "Orders" },
  { id: "seller_onboarding", label: "Seller Verification Status", icon: FileCheck2, badge: "Verified" },
  { id: "organisations", label: "Dealership & Teams", icon: Building2, badge: "Organisation" },
  { id: "my_tickets", label: "Help & Support", icon: Headphones, badge: "Help" },
  { id: "profile", label: "My Profile", icon: User },
];

export const WORKSHOP_NAV_ITEMS: NavItem[] = [
  { id: "workshop_landing", label: "Workshop Operations Hub", icon: Wrench, badge: "Workshop" },
  { id: "workshop_settlements", label: "Settlements & Invoices", icon: Receipt, badge: "Finance" },
  { id: "workshops_browse", label: "Workshops Directory", icon: Wrench, badge: "Directory" },
  { id: "seller_onboarding", label: "Workshop Partner Status", icon: FileCheck2, badge: "Partner" },
  { id: "organisations", label: "Workshop & Teams", icon: Building2, badge: "Organisation" },
  { id: "my_tickets", label: "Help & Support", icon: Headphones, badge: "Help" },
  { id: "profile", label: "My Profile", icon: User },
];

export const ADMIN_NAV_ITEMS: NavItem[] = [
  { id: "admin_overview", label: "Admin Overview", icon: LayoutDashboard, badge: "Live" },
  { id: "admin_marketplace_review", label: "Marketplace Moderation", icon: ShieldCheck, badge: "Review" },
  { id: "admin_sellers", label: "Seller Management", icon: Store, badge: "Sellers" },
  { id: "admin_workshops", label: "Workshop Management", icon: Wrench, badge: "Workshops" },
  { id: "admin_buyers", label: "Buyer Management", icon: Users, badge: "Buyers" },
  { id: "admin_orders_monitoring", label: "Customer Orders", icon: Boxes, badge: "Orders" },
  { id: "admin_disputes_refunds", label: "Disputes & Refunds", icon: Scale, badge: "Disputes" },
  { id: "admin_staff_management", label: "Staff Management", icon: UserPlus, badge: "Staff" },
  { id: "organisations", label: "Organisations & Teams", icon: Building2, badge: "Admin" },
  { id: "support_overview", label: "Support Operations", icon: Headphones, badge: "Support" },
  { id: "commercial_admin", label: "Commercial Control Plane", icon: Landmark, badge: "R1" },
  { id: "profile", label: "My Profile", icon: User },
];

export function getStaffNavItems(user?: PrototypeUser | null): NavItem[] {
  const staffRoleCode = user?.staff_role?.code?.toUpperCase();
  const userPerms = Array.isArray(user?.permissions) ? user.permissions : [];
  const hasPerm = (p: string) => userPerms.includes(p);

  const staffItems: NavItem[] = [];

  if (hasPerm("listing.review") || staffRoleCode === "VERIFICATION_OFFICER") {
    staffItems.push({ id: "admin_marketplace_review", label: "Marketplace Moderation", icon: ShieldCheck, badge: "Review" });
  }

  if (hasPerm("seller.verify") || staffRoleCode === "VERIFICATION_OFFICER") {
    staffItems.push({ id: "seller_reviews", label: "Seller Applications Queue", icon: FileCheck2, badge: "Review" });
  }

  if (hasPerm("dispute.manage") || hasPerm("order.refund") || staffRoleCode === "DISPUTE_MANAGER" || staffRoleCode === "FINANCE_OFFICER") {
    staffItems.push({ id: "admin_disputes_refunds", label: "Disputes & Refunds", icon: Scale, badge: "Disputes" });
  }

  if (hasPerm("finance.payout") || staffRoleCode === "FINANCE_OFFICER") {
    staffItems.push({ id: "admin_approvals", label: "Finance & Approvals", icon: CheckCircle2, badge: "Approvals" });
  }

  if (hasPerm("support.ticket.manage") || staffRoleCode === "SUPPORT_AGENT") {
    staffItems.push({ id: "support_overview", label: "Support Operations", icon: Headphones, badge: "Support" });
  }

  staffItems.push({ id: "admin_workshop_oversight", label: "Workshop Oversight", icon: ClipboardCheck, badge: "Audit" });
  staffItems.push({ id: "organisations", label: "Organisations & Teams", icon: Building2, badge: "Operations" });
  staffItems.push({ id: "profile", label: "My Profile", icon: User });

  return staffItems;
}

export function getNavItemsForRole(activeRole: string, user?: PrototypeUser | null): NavItem[] {
  const normRole = (activeRole || "").toUpperCase();
  switch (normRole) {
    case "ADMIN":
      return ADMIN_NAV_ITEMS;
    case "STAFF":
      return getStaffNavItems(user);
    case "SELLER":
      return SELLER_NAV_ITEMS;
    case "WORKSHOP":
      return WORKSHOP_NAV_ITEMS;
    case "BUYER":
    default:
      return BUYER_NAV_ITEMS;
  }
}

export function getDefaultTabForRole(activeRole: string, user?: PrototypeUser | null): string {
  const normRole = (activeRole || "").toUpperCase();
  switch (normRole) {
    case "ADMIN":
      return "admin_overview";
    case "STAFF": {
      const staffRoleCode = user?.staff_role?.code?.toUpperCase();
      switch (staffRoleCode) {
        case "DISPUTE_MANAGER":
          return "admin_disputes_refunds";
        case "FINANCE_OFFICER":
          return "admin_approvals";
        case "VERIFICATION_OFFICER":
          return "admin_marketplace_review";
        case "SUPPORT_AGENT":
          return "support_overview";
        default:
          return "admin_workshop_oversight";
      }
    }
    case "SELLER":
      return "seller_inventory";
    case "WORKSHOP":
      return "workshop_landing";
    case "BUYER":
    default:
      return "marketplace_browse";
  }
}

export function isTabAllowedForRole(tabId: string, activeRole: string, user?: PrototypeUser | null): boolean {
  const normRole = (activeRole || "").toUpperCase();

  // Common universal profile tabs
  if (tabId === "profile" || tabId === "organisations") {
    return true;
  }

  // Admin has access to all admin items plus legacy moderation tabs
  if (normRole === "ADMIN") {
    return (
      ADMIN_NAV_ITEMS.some((i) => i.id === tabId) ||
      tabId === "admin_approvals" ||
      tabId === "admin_workshop_oversight" ||
      tabId === "seller_reviews"
    );
  }

  // Staff has access to staff nav items
  if (normRole === "STAFF") {
    return getStaffNavItems(user).some((i) => i.id === tabId);
  }

  // Seller tabs
  if (normRole === "SELLER") {
    if (tabId === "seller_disputes") return true; // maps into seller_orders
    return SELLER_NAV_ITEMS.some((i) => i.id === tabId);
  }

  // Workshop tabs
  if (normRole === "WORKSHOP") {
    return WORKSHOP_NAV_ITEMS.some((i) => i.id === tabId);
  }

  // Buyer tabs (default)
  return BUYER_NAV_ITEMS.some((i) => i.id === tabId);
}

export const TAB_LABELS: Record<string, string> = {
  admin_overview: "Admin Platform Overview & Analytics",
  admin_sellers: "Seller Account Directory & Verification",
  admin_workshops: "Workshop Network & Operations",
  admin_buyers: "Buyer Accounts & Activity Governance",
  admin_orders_monitoring: "Platform Orders Monitoring & Fulfillment",
  marketplace_browse: "Marketplace — Vehicles & Spare Parts",
  my_orders: "My Orders & Vehicle Purchases",
  buyer_returns_refunds: "My Returns & Refunds",
  favourites: "Saved Vehicles & Spare Parts",
  my_enquiries: "Direct Dealership Enquiries",
  seller_inventory: "Seller Inventory Management",
  seller_orders: "Customer Orders & Returns",
  seller_disputes: "Customer Disputes & Mediation",
  admin_marketplace_review: "Marketplace Moderation & Approval",
  admin_disputes_refunds: "Platform Dispute Resolution & Refunds",
  admin_staff_management: "Platform Staff Directory & RBAC",
  admin_workshop_oversight: "Workshop Operations & Compliance",
  admin_approvals: "Maker-Checker Financial Approvals",
  support_overview: "Customer Support Agent Workspace",
  commercial_admin: "Commercial Control Plane (SKUs & Rates)",
  profile: "Account Profile & Security",
  organisations: "Organisations & Teams",
  my_tickets: "Help & Support Tickets",
  garage: "My Garage — Vehicle Management",
  catalogue: "Vehicle & Parts Catalogue",
  parts_fitment: "Vehicle Parts & Fitment Verification",
  seller_onboarding: "Apply to sell / Apply as workshop",
  seller_reviews: "Seller Applications Compliance Queue",
  workshop_landing: "Workshop Services — Workshop Partner Hub",
  workshop_settlements: "Workshop Settlements & Invoices",
  workshops_browse: "Workshop Services & Bookings",
};

export function getTabLabel(tabId: string): string {
  return TAB_LABELS[tabId] || "Dashboard Overview";
}

