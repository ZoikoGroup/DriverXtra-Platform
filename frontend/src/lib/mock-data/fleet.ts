// Canonical Fleet Portfolio & Operations Grounded in Doc 16

export interface FleetVehicleItem {
  id: string;
  vin: string;
  registrationPlate: string;
  unitCode: string;
  vehicleDisplay: string;
  assignedDriver: string;
  assignedPool: string;
  operationalStatus: "ACTIVE_SERVICE" | "MAINTENANCE_DUE" | "GROUNDED_DEFECT" | "DISPOSAL_PREP";
  currentMileage: number;
  lastInspectionDate: string;
  nextServiceDueDate: string;
  monthlyOperatingCost: number;
}

export const MOCK_FLEET_VEHICLES: FleetVehicleItem[] = [
  {
    id: "flt_001",
    vin: "VF1MA00056192841",
    registrationPlate: "LD23 FLT",
    unitCode: "VAN-081",
    vehicleDisplay: "2023 Renault Master LM35 dCi 135 Business",
    assignedDriver: "Thomas Wright (Badge #492)",
    assignedPool: "London Metro Express",
    operationalStatus: "ACTIVE_SERVICE",
    currentMileage: 42100,
    lastInspectionDate: "2026-08-14",
    nextServiceDueDate: "2026-11-15",
    monthlyOperatingCost: 340
  },
  {
    id: "flt_002",
    vin: "W1V9076331P819203",
    registrationPlate: "LD23 MBZ",
    unitCode: "VAN-082",
    vehicleDisplay: "2023 Mercedes-Benz Sprinter 315 CDI Progressive",
    assignedDriver: "Amir Khan (Badge #118)",
    assignedPool: "South East Inter-City",
    operationalStatus: "MAINTENANCE_DUE",
    currentMileage: 58900,
    lastInspectionDate: "2026-06-20",
    nextServiceDueDate: "2026-10-18",
    monthlyOperatingCost: 410
  },
  {
    id: "flt_003",
    vin: "JTMB1RFV50D198214",
    registrationPlate: "LO24 XTR",
    unitCode: "CAR-014",
    vehicleDisplay: "2024 Toyota RAV4 2.5 Hybrid Design AWD",
    assignedDriver: "Rachel Adams (Supervisor)",
    assignedPool: "Regional Supervision Pool",
    operationalStatus: "ACTIVE_SERVICE",
    currentMileage: 11400,
    lastInspectionDate: "2026-09-02",
    nextServiceDueDate: "2027-03-01",
    monthlyOperatingCost: 280
  }
];
