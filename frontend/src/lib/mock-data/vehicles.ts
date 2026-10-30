// Canonical Vehicle Master & My Garage Data Model Grounded in Doc 05 & Doc 03

export interface ServiceRecord {
  id: string;
  date: string;
  mileage: number;
  serviceType: string;
  workshopName: string;
  workshopId: string;
  invoiceRef: string;
  verifiedWriteBack: boolean;
  notes: string;
  cost: number;
}

export interface VehicleInstance {
  id: string;              // UUIDv7 as per Doc 03
  vin: string;
  registrationPlate: string;
  make: string;
  model: string;
  year: number;
  trim: string;
  engineCode: string;
  fuelType: "PETROL" | "DIESEL" | "HYBRID" | "EV";
  transmission: "AUTOMATIC" | "MANUAL" | "DUAL_CLUTCH";
  powerBhp: number;
  currentOdometer: number;
  motExpiryDate: string;
  motStatus: "VALID" | "EXPIRED" | "ADVISORY_PRESENT";
  activeRecallsCount: number;
  ownershipStatus: "VERIFIED_OWNER" | "DEALER_INVENTORY" | "FLEET_ASSET";
  primaryImageUrl: string;
  serviceHistory: ServiceRecord[];
}

export const MOCK_GARAGE_VEHICLES: VehicleInstance[] = [
  {
    id: "veh_01j7x001bmw330",
    vin: "WBA5R1C50M8219420",
    registrationPlate: "GF21 XTR",
    make: "BMW",
    model: "3 Series Saloon",
    year: 2021,
    trim: "330i M Sport (Pro Pack)",
    engineCode: "B48B20",
    fuelType: "PETROL",
    transmission: "AUTOMATIC",
    powerBhp: 258,
    currentOdometer: 34820,
    motExpiryDate: "2027-10-14",
    motStatus: "VALID",
    activeRecallsCount: 0,
    ownershipStatus: "VERIFIED_OWNER",
    primaryImageUrl: "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=800&q=80",
    serviceHistory: [
      {
        id: "srv_98421",
        date: "2026-09-12",
        mileage: 31450,
        serviceType: "Major Scheduled Service & Brake Fluid",
        workshopName: "Apex Bavarian Performance & MOT Centre",
        workshopId: "org_wksh_0419",
        invoiceRef: "WO-98421",
        verifiedWriteBack: true,
        notes: "Full synthetic 0W-30 oil change, spark plugs, brake fluid flush. All electronic diagnostics cleared.",
        cost: 289
      },
      {
        id: "srv_94102",
        date: "2026-06-04",
        mileage: 27810,
        serviceType: "Front Brake Pads & Sensor Replacement",
        workshopName: "Apex Bavarian Performance & MOT Centre",
        workshopId: "org_wksh_0419",
        invoiceRef: "WO-94102",
        verifiedWriteBack: true,
        notes: "Brembo Prime pads installed. Guaranteed fitment verified via catalogue compatibility.",
        cost: 215
      },
      {
        id: "srv_88201",
        date: "2025-10-15",
        mileage: 21900,
        serviceType: "Annual Statutory MOT Inspection",
        workshopName: "DVLA Testing Bay SW1",
        workshopId: "org_dvla_bay",
        invoiceRef: "MOT-2025-081",
        verifiedWriteBack: true,
        notes: "Pass with zero defects and zero advisories.",
        cost: 45
      }
    ]
  },
  {
    id: "veh_01j7x002golfgti",
    vin: "WVWZZZAUZJP081923",
    registrationPlate: "LT19 VAG",
    make: "Volkswagen",
    model: "Golf",
    year: 2019,
    trim: "GTI Performance 245PS DSG",
    engineCode: "EA888",
    fuelType: "PETROL",
    transmission: "DUAL_CLUTCH",
    powerBhp: 245,
    currentOdometer: 48100,
    motExpiryDate: "2027-04-20",
    motStatus: "VALID",
    activeRecallsCount: 0,
    ownershipStatus: "VERIFIED_OWNER",
    primaryImageUrl: "https://images.unsplash.com/photo-1541899481282-d53bffe3c35d?auto=format&fit=crop&w=800&q=80",
    serviceHistory: [
      {
        id: "srv_77201",
        date: "2026-03-10",
        mileage: 44200,
        serviceType: "DSG Transmission Service & Haldex Oil",
        workshopName: "Precision Master Mechanics",
        workshopId: "org_wksh_0211",
        invoiceRef: "WO-77201",
        verifiedWriteBack: true,
        notes: "DSG fluid and filter replacement. Adaptation reset complete.",
        cost: 320
      }
    ]
  }
];
