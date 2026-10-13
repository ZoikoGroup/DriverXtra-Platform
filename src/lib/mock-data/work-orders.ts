// Canonical Automotive Services & Work Order Data Model Grounded in Doc 13

export type WorkOrderStatus =
  | "CREATED"
  | "AUTHORIZED"
  | "IN_PROGRESS"
  | "WAITING_APPROVAL"
  | "WAITING_PARTS"
  | "COMPLETED"
  | "CLOSED";

export interface ChangeOrderRecord {
  id: string;
  itemDescription: string;
  additionalCost: number;
  reason: string;
  photoEvidenceUrl?: string;
  status: "PROPOSED_PENDING_CUSTOMER" | "CUSTOMER_AUTHORIZED" | "CUSTOMER_REJECTED";
  proposedAt: string;
  authorizedAt?: string;
}

export interface WorkshopWorkOrder {
  id: string;
  bookingRef: string;
  customerName: string;
  customerPhone: string;
  vehicleInstanceId: string;
  vehicleDisplay: string;
  registrationPlate: string;
  currentOdometerRecorded: number;
  serviceType: string;
  bayName: string;
  assignedTechnician: string;
  status: WorkOrderStatus;
  initialAuthorizedPrice: number;
  finalPrice: number;
  notes: string;
  scheduledDate: string;
  changeOrders: ChangeOrderRecord[];
}

export const MOCK_WORK_ORDERS: WorkshopWorkOrder[] = [
  {
    id: "WO-98421",
    bookingRef: "BK-88410",
    customerName: "Mark Harrison",
    customerPhone: "+44 7700 900123",
    vehicleInstanceId: "veh_01j7x001bmw330",
    vehicleDisplay: "2021 BMW 3 Series 330i M Sport",
    registrationPlate: "GF21 XTR",
    currentOdometerRecorded: 34820,
    serviceType: "Major Scheduled Service + Statutory MOT",
    bayName: "Bay 3 (Lift A)",
    assignedTechnician: "David Kowalski (Master Tech)",
    status: "IN_PROGRESS",
    initialAuthorizedPrice: 289,
    finalPrice: 289,
    notes: "Customer authorized initial quote. Brake fluid flush completed. Performing electronic reset.",
    scheduledDate: "2026-10-13",
    changeOrders: []
  },
  {
    id: "WO-98422",
    bookingRef: "BK-88411",
    customerName: "Sarah Jenkins",
    customerPhone: "+44 7700 900456",
    vehicleInstanceId: "veh_01j7x003tesla",
    vehicleDisplay: "2023 Tesla Model 3 Long Range",
    registrationPlate: "LO23 FGH",
    currentOdometerRecorded: 19400,
    serviceType: "Cabin Filtration & High-Voltage Health Scan",
    bayName: "Bay 1 (Dedicated EV Bay)",
    assignedTechnician: "Liam O'Connor (EV Certified)",
    status: "WAITING_APPROVAL",
    initialAuthorizedPrice: 165,
    finalPrice: 199,
    notes: "ChangeOrder #CO-02 dispatched to customer app: Worn front wiper blades (£34). Awaiting customer tap.",
    scheduledDate: "2026-10-13",
    changeOrders: [
      {
        id: "CO-02",
        itemDescription: "Bosch Aerotwin Front Wiper Blade Set (Pair)",
        additionalCost: 34,
        reason: "Excessive streak tearing observed during rain sensor test.",
        status: "PROPOSED_PENDING_CUSTOMER",
        proposedAt: "2026-10-13T10:15:00Z"
      }
    ]
  },
  {
    id: "WO-98423",
    bookingRef: "BK-88412",
    customerName: "Michael Patel",
    customerPhone: "+44 7700 900789",
    vehicleInstanceId: "veh_01j7x004audi",
    vehicleDisplay: "2020 Audi A4 Avant 2.0 TDI",
    registrationPlate: "KW20 BCD",
    currentOdometerRecorded: 52100,
    serviceType: "Front Brake Pads & Rotor Replacement",
    bayName: "Bay 4 (General Lift)",
    assignedTechnician: "Alex Reed",
    status: "WAITING_PARTS",
    initialAuthorizedPrice: 340,
    finalPrice: 340,
    notes: "Brembo rotors arriving via parts carrier dispatch by 14:00 today.",
    scheduledDate: "2026-10-13",
    changeOrders: []
  }
];
