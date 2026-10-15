// Canonical Catalog & Fitment Data Model Grounded in Doc 06

export interface CatalogPart {
  id: string;
  name: string;
  brand: string;
  mpn: string;               // Manufacturer Part Number
  category: string;
  subCategory: string;
  price: number;
  fitsSelectedVehicle: boolean;
  fitmentConfidence: "VERIFIED_OEM" | "SUPPLIER_ASSERTION" | "UNIVERSAL";
  sellerCount: number;
  inStockQuantity: number;
  leadTimeDays: number;
  oemCrossReferences: string[];
}

export const MOCK_CATALOG_PARTS: CatalogPart[] = [
  {
    id: "cat_brembo_09c398",
    name: "Brembo Prime Two-Piece Front Brake Disc Rotor Set (348mm)",
    brand: "Brembo",
    mpn: "09.C398.13",
    category: "Braking Systems",
    subCategory: "Brake Rotors",
    price: 215,
    fitsSelectedVehicle: true,
    fitmentConfidence: "VERIFIED_OEM",
    sellerCount: 4,
    inStockQuantity: 18,
    leadTimeDays: 1,
    oemCrossReferences: ["BMW 34116860911", "BMW 34116860912"]
  },
  {
    id: "cat_bosch_s5a13",
    name: "Bosch S5 A13 AGM Heavy Duty Stop-Start Battery (95Ah 850A)",
    brand: "Bosch",
    mpn: "0 092 S5A 130",
    category: "Electrical & Ignition",
    subCategory: "Batteries",
    price: 184,
    fitsSelectedVehicle: true,
    fitmentConfidence: "VERIFIED_OEM",
    sellerCount: 6,
    inStockQuantity: 34,
    leadTimeDays: 1,
    oemCrossReferences: ["BMW 61216924023", "VAG 000915105CE"]
  },
  {
    id: "cat_michelin_ps4s",
    name: "Michelin Pilot Sport 4S High Performance Tire 255/35 R19 96Y XL",
    brand: "Michelin",
    mpn: "MIC-784912",
    category: "Wheels & Tires",
    subCategory: "Performance Tires",
    price: 198,
    fitsSelectedVehicle: true,
    fitmentConfidence: "VERIFIED_OEM",
    sellerCount: 3,
    inStockQuantity: 22,
    leadTimeDays: 2,
    oemCrossReferences: ["OEM Fitment Grade BMW *"]
  },
  {
    id: "cat_kn_filter",
    name: "K&N High-Flow Replacement Engine Air Filter Element",
    brand: "K&N Engineering",
    mpn: "33-3136",
    category: "Engine & Filtration",
    subCategory: "Air Filters",
    price: 68,
    fitsSelectedVehicle: true,
    fitmentConfidence: "SUPPLIER_ASSERTION",
    sellerCount: 5,
    inStockQuantity: 12,
    leadTimeDays: 1,
    oemCrossReferences: ["BMW 13718635102"]
  }
];
