// Canonical Inventory & Offer Data Model Grounded in Doc 07 & Doc 16

export interface InventoryItem {
  id: string;
  vehicleInstanceId: string;
  title: string;
  vin: string;
  registrationPlate: string;
  year: number;
  make: string;
  model: string;
  price: number;
  monthlyPcp: number;
  costBasis: number;
  mileage: number;
  transmission: string;
  fuel: string;
  listingStatus: "ACTIVE" | "RESERVED" | "SOLD" | "PENDING_MODERATION" | "DRAFT";
  inventoryStatus: "AVAILABLE" | "COMMITTED" | "HELD_ESCROW";
  ingestionSource: "DMS_AUTOSYNC" | "BULK_FEED_CSV" | "DIRECT_WIZARD";
  daysInStock: number;
  leadCount: number;
  escrowDepositHeld: number;
  primaryImageUrl: string;
  dealerOrganizationId: string;
}

export const MOCK_DEALER_INVENTORY: InventoryItem[] = [
  {
    id: "inv_01j7x_toyota_rav4",
    vehicleInstanceId: "veh_jtmb1rfv50d",
    title: "2024 Toyota RAV4 2.5 Hybrid Design AWD",
    vin: "JTMB1RFV50D198214",
    registrationPlate: "LO24 XTR",
    year: 2024,
    make: "Toyota",
    model: "RAV4 Hybrid",
    price: 34995,
    monthlyPcp: 429,
    costBasis: 31200,
    mileage: 8200,
    transmission: "Automatic",
    fuel: "Hybrid Petrol",
    listingStatus: "ACTIVE",
    inventoryStatus: "AVAILABLE",
    ingestionSource: "DMS_AUTOSYNC",
    daysInStock: 8,
    leadCount: 7,
    escrowDepositHeld: 0,
    primaryImageUrl: "https://images.unsplash.com/photo-1581540222194-0def2dda95b8?auto=format&fit=crop&w=800&q=80",
    dealerOrganizationId: "org_dealer_0182"
  },
  {
    id: "inv_01j7x_bmw_x3",
    vehicleInstanceId: "veh_wba5r1c50m8",
    title: "2023 BMW X3 xDrive30e M Sport (Pro Pack)",
    vin: "WBA5R1C50M8249102",
    registrationPlate: "KP23 BBA",
    year: 2023,
    make: "BMW",
    model: "X3 xDrive30e",
    price: 43500,
    monthlyPcp: 549,
    costBasis: 39000,
    mileage: 14600,
    transmission: "Automatic",
    fuel: "Plug-in Hybrid",
    listingStatus: "ACTIVE",
    inventoryStatus: "AVAILABLE",
    ingestionSource: "DMS_AUTOSYNC",
    daysInStock: 14,
    leadCount: 12,
    escrowDepositHeld: 0,
    primaryImageUrl: "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=800&q=80",
    dealerOrganizationId: "org_dealer_0182"
  },
  {
    id: "inv_01j7x_merc_c300",
    vehicleInstanceId: "veh_w1k2060461f",
    title: "2024 Mercedes-Benz C 300 AMG Line Premium",
    vin: "W1K2060461F091823",
    registrationPlate: "RJ24 MBZ",
    year: 2024,
    make: "Mercedes-Benz",
    model: "C 300 AMG Line",
    price: 39800,
    monthlyPcp: 495,
    costBasis: 36000,
    mileage: 6300,
    transmission: "9G-Tronic",
    fuel: "Mild Hybrid Petrol",
    listingStatus: "RESERVED",
    inventoryStatus: "HELD_ESCROW",
    ingestionSource: "DIRECT_WIZARD",
    daysInStock: 4,
    leadCount: 4,
    escrowDepositHeld: 500,
    primaryImageUrl: "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=800&q=80",
    dealerOrganizationId: "org_dealer_0182"
  },
  {
    id: "inv_01j7x_porsche_macan",
    vehicleInstanceId: "veh_wp1zzz95znl",
    title: "2022 Porsche Macan GTS PDK (Sport Chrono)",
    vin: "WP1ZZZ95ZNL821094",
    registrationPlate: "GT22 POR",
    year: 2022,
    make: "Porsche",
    model: "Macan GTS",
    price: 57900,
    monthlyPcp: 720,
    costBasis: 52000,
    mileage: 22100,
    transmission: "Dual-Clutch PDK",
    fuel: "Twin-Turbo Petrol",
    listingStatus: "ACTIVE",
    inventoryStatus: "AVAILABLE",
    ingestionSource: "BULK_FEED_CSV",
    daysInStock: 21,
    leadCount: 16,
    escrowDepositHeld: 0,
    primaryImageUrl: "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80",
    dealerOrganizationId: "org_dealer_0182"
  }
];
