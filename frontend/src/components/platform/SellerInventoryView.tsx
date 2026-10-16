"use client";

import React, { useState, useEffect } from "react";
import {
  api,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  VehicleMake,
  VehicleModel,
  VehicleVariant,
  PartCategory,
  BackendOrganisation,
  CreateVehicleListingPayload,
  CreatePartListingPayload,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Car,
  Wrench,
  Plus,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  ShieldAlert,
  X,
  Building2,
  FileText,
} from "lucide-react";

export default function SellerInventoryView() {
  const { user } = useAuth();
  const [activeSection, setActiveSection] = useState<"vehicles" | "parts">("vehicles");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  // Vehicles state
  const [vehicles, setVehicles] = useState<MarketplaceVehicleListing[]>([]);
  const [vehiclesLoading, setVehiclesLoading] = useState(false);
  const [addVehicleOpen, setAddVehicleOpen] = useState(false);

  // Parts state
  const [parts, setParts] = useState<MarketplacePartListing[]>([]);
  const [partsLoading, setPartsLoading] = useState(false);
  const [addPartOpen, setAddPartOpen] = useState(false);

  // Reference data
  const [makes, setMakes] = useState<VehicleMake[]>([]);
  const [models, setModels] = useState<VehicleModel[]>([]);
  const [variants, setVariants] = useState<VehicleVariant[]>([]);
  const [categories, setCategories] = useState<PartCategory[]>([]);
  const [userOrgs, setUserOrgs] = useState<BackendOrganisation[]>([]);

  // Feedback states
  const [actionLoading, setActionLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [vehModalError, setVehModalError] = useState("");
  const [partModalError, setPartModalError] = useState("");

  // New Vehicle Form State
  const [vehTitle, setVehTitle] = useState("");
  const [vehMake, setVehMake] = useState("");
  const [vehModel, setVehModel] = useState("");
  const [vehVariant, setVehVariant] = useState("");
  const [vehYear, setVehYear] = useState("2021");
  const [vehReg, setVehReg] = useState("");
  const [vehVin, setVehVin] = useState("");
  const [vehMileage, setVehMileage] = useState("25000");
  const [vehFuel, setVehFuel] = useState("PETROL");
  const [vehTrans, setVehTrans] = useState("AUTOMATIC");
  const [vehBody, setVehBody] = useState("Saloon");
  const [vehPrice, setVehPrice] = useState("18500");
  const [vehCondition, setVehCondition] = useState("VERY_GOOD");
  const [vehDescription, setVehDescription] = useState("");
  const [vehImageUrl, setVehImageUrl] = useState("");
  const [vehCity, setVehCity] = useState("London");
  const [vehPostcode, setVehPostcode] = useState("SW1A 1AA");
  const [vehOrg, setVehOrg] = useState("");

  // New Part Form State
  const [partName, setPartName] = useState("");
  const [partBrand, setPartBrand] = useState("");
  const [partMpn, setPartMpn] = useState("");
  const [partOem, setPartOem] = useState("");
  const [partCategory, setPartCategory] = useState("");
  const [partPrice, setPartPrice] = useState("120.00");
  const [partStock, setPartStock] = useState("5");
  const [partCondition, setPartCondition] = useState("NEW");
  const [partDescription, setPartDescription] = useState("");
  const [partImageUrl, setPartImageUrl] = useState("");
  const [partVariant, setPartVariant] = useState("");
  const [partCompatibilityNotes, setPartCompatibilityNotes] = useState("");
  const [partOrg, setPartOrg] = useState("");

  const resetVehicleForm = () => {
    setVehTitle("");
    setVehMake("");
    setVehModel("");
    setVehVariant("");
    setModels([]);
    setVariants([]);
    setVehYear("2021");
    setVehReg("");
    setVehVin("");
    setVehMileage("25000");
    setVehFuel("PETROL");
    setVehTrans("AUTOMATIC");
    setVehBody("Saloon");
    setVehPrice("18500");
    setVehCondition("VERY_GOOD");
    setVehDescription("");
    setVehImageUrl("");
    setVehCity("London");
    setVehPostcode("SW1A 1AA");
    setVehModalError("");
  };

  const resetPartForm = () => {
    setPartName("");
    setPartBrand("");
    setPartMpn("");
    setPartOem("");
    setPartCategory("");
    setPartPrice("120.00");
    setPartStock("5");
    setPartCondition("NEW");
    setPartDescription("");
    setPartImageUrl("");
    setPartVariant("");
    setPartCompatibilityNotes("");
    setPartModalError("");
  };

  // Load reference datasets
  useEffect(() => {
    api.catalogue.getMakes().then(setMakes).catch(console.error);
    api.catalogue.getCategories().then(setCategories).catch(console.error);
    api.organisations.list().then((paginated) => {
      const orgs = paginated.results || [];
      // Filter to user's organisations where they have admin/owner permission
      const authorized = orgs.filter(
        (o) => o.user_role === "OWNER" || o.user_role === "ADMIN" || user?.is_staff || user?.is_superuser
      );
      setUserOrgs(authorized);
      if (authorized.length > 0) {
        setVehOrg(authorized[0].id);
        setPartOrg(authorized[0].id);
      }
    }).catch(console.error);
  }, [user]);

  // Load models when vehicle make changes
  useEffect(() => {
    if (!vehMake) return;
    let ignore = false;
    api.catalogue.getModels(vehMake).then((res) => {
      if (!ignore) setModels(res);
    }).catch(console.error);
    return () => {
      ignore = true;
    };
  }, [vehMake]);

  // Load variants when model changes
  useEffect(() => {
    if (!vehModel) return;
    let ignore = false;
    api.catalogue.getVariants(vehModel).then((res) => {
      if (!ignore) setVariants(res);
    }).catch(console.error);
    return () => {
      ignore = true;
    };
  }, [vehModel]);

  // Fetch Seller's Inventory
  useEffect(() => {
    let ignore = false;
    const statusParam = statusFilter === "ALL" ? undefined : statusFilter;
    if (activeSection === "vehicles") {
      api.marketplace.listMyVehicles(statusParam).then((data) => {
        if (!ignore) {
          setVehicles(data);
          setVehiclesLoading(false);
        }
      }).catch((err) => {
        if (!ignore) {
          console.error("Failed to load seller vehicles", err);
          setVehiclesLoading(false);
        }
      });
    } else {
      api.marketplace.listMyParts(statusParam).then((data) => {
        if (!ignore) {
          setParts(data);
          setPartsLoading(false);
        }
      }).catch((err) => {
        if (!ignore) {
          console.error("Failed to load seller parts", err);
          setPartsLoading(false);
        }
      });
    }
    return () => {
      ignore = true;
    };
  }, [activeSection, statusFilter]);

  // Submit New Vehicle
  const handleSubmitVehicle = async (asDraft: boolean) => {
    setVehModalError("");
    setErrorMessage("");
    setSuccessMessage("");

    if (!vehTitle.trim()) {
      setVehModalError("Listing Title is required.");
      return;
    }
    if (!vehMake) {
      setVehModalError("Please select a Vehicle Make.");
      return;
    }
    if (!vehModel) {
      setVehModalError("Please select a Vehicle Model.");
      return;
    }
    const parsedPrice = parseFloat(vehPrice);
    if (isNaN(parsedPrice) || parsedPrice <= 0) {
      setVehModalError("Asking price must be greater than £0.00.");
      return;
    }
    const parsedYear = parseInt(vehYear, 10);
    if (isNaN(parsedYear) || parsedYear < 1900 || parsedYear > 2050) {
      setVehModalError("Please provide a valid manufacturing year (1900 - 2050).");
      return;
    }

    setActionLoading(true);
    try {
      const payload: CreateVehicleListingPayload = {
        title: vehTitle.trim(),
        make: vehMake,
        model: vehModel,
        variant: vehVariant || undefined,
        year: parsedYear,
        registration_number: vehReg.trim(),
        vin: vehVin.trim(),
        mileage: parseInt(vehMileage, 10) || 0,
        fuel_type: vehFuel,
        transmission: vehTrans,
        body_type: vehBody.trim(),
        price: parsedPrice,
        currency: "GBP",
        condition: vehCondition,
        description: vehDescription.trim(),
        primary_image_url: vehImageUrl.trim(),
        location_city: vehCity.trim(),
        location_postcode: vehPostcode.trim(),
        organisation: vehOrg || null,
        status: asDraft ? "DRAFT" : "PENDING_APPROVAL",
      };

      await api.marketplace.createVehicle(payload);
      setSuccessMessage(
        asDraft
          ? "Vehicle saved to draft inventory."
          : "Vehicle submitted successfully! It is now Pending Approval by marketplace compliance."
      );
      setAddVehicleOpen(false);
      resetVehicleForm();
      const targetFilter = asDraft ? "DRAFT" : "PENDING_APPROVAL";
      setStatusFilter(targetFilter);
      const data = await api.marketplace.listMyVehicles(targetFilter);
      setVehicles(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit vehicle.";
      setVehModalError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Submit New Spare Part
  const handleSubmitPart = async (asDraft: boolean) => {
    setPartModalError("");
    setErrorMessage("");
    setSuccessMessage("");

    if (!partName.trim()) {
      setPartModalError("Part Name is required.");
      return;
    }
    if (!partBrand.trim()) {
      setPartModalError("Brand / Manufacturer is required.");
      return;
    }
    if (!partMpn.trim()) {
      setPartModalError("MPN (Manufacturer Part Number) is required.");
      return;
    }
    if (!partCategory) {
      setPartModalError("Please select a Taxonomy Category.");
      return;
    }
    const parsedPrice = parseFloat(partPrice);
    if (isNaN(parsedPrice) || parsedPrice <= 0) {
      setPartModalError("Part price must be greater than £0.00.");
      return;
    }
    const parsedStock = parseInt(partStock, 10);
    if (isNaN(parsedStock) || parsedStock < 0) {
      setPartModalError("Stock quantity cannot be negative.");
      return;
    }

    setActionLoading(true);
    try {
      const oemList = partOem
        ? partOem.split(",").map((s) => s.trim()).filter(Boolean)
        : [];

      const payload: CreatePartListingPayload = {
        name: partName.trim(),
        brand: partBrand.trim(),
        mpn: partMpn.trim(),
        oem_numbers: oemList,
        category: partCategory,
        price: parsedPrice,
        currency: "GBP",
        stock_quantity: parsedStock,
        condition: partCondition,
        description: partDescription.trim(),
        primary_image_url: partImageUrl.trim(),
        compatible_variants: partVariant ? [partVariant] : [],
        compatibility_notes: partCompatibilityNotes.trim(),
        organisation: partOrg || null,
        status: asDraft ? "DRAFT" : "PENDING_APPROVAL",
      };

      await api.marketplace.createPart(payload);
      setSuccessMessage(
        asDraft
          ? "Spare part saved to draft inventory."
          : "Spare part submitted successfully! It is now Pending Approval by compliance."
      );
      setAddPartOpen(false);
      resetPartForm();
      const targetFilter = asDraft ? "DRAFT" : "PENDING_APPROVAL";
      setStatusFilter(targetFilter);
      const data = await api.marketplace.listMyParts(targetFilter);
      setParts(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit spare part.";
      setPartModalError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Submit Draft Vehicle For Approval
  const handlePublishDraftVehicle = async (id: string) => {
    setActionLoading(true);
    setErrorMessage("");
    try {
      await api.marketplace.submitVehicle(id);
      setSuccessMessage("Draft vehicle submitted for marketplace compliance approval!");
      setStatusFilter("PENDING_APPROVAL");
      const data = await api.marketplace.listMyVehicles("PENDING_APPROVAL");
      setVehicles(data);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to submit draft vehicle.");
    } finally {
      setActionLoading(false);
    }
  };

  // Submit Draft Part For Approval
  const handlePublishDraftPart = async (id: string) => {
    setActionLoading(true);
    setErrorMessage("");
    try {
      await api.marketplace.submitPart(id);
      setSuccessMessage("Draft spare part submitted for marketplace compliance approval!");
      setStatusFilter("PENDING_APPROVAL");
      const data = await api.marketplace.listMyParts("PENDING_APPROVAL");
      setParts(data);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to submit draft spare part.");
    } finally {
      setActionLoading(false);
    }
  };

  // Resubmit vehicle
  const handleResubmitVehicle = async (id: string) => {
    setActionLoading(true);
    setErrorMessage("");
    try {
      await api.marketplace.resubmitVehicle(id);
      setSuccessMessage("Vehicle resubmitted for admin review.");
      setStatusFilter("PENDING_APPROVAL");
      const data = await api.marketplace.listMyVehicles("PENDING_APPROVAL");
      setVehicles(data);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Resubmission failed.");
    } finally {
      setActionLoading(false);
    }
  };

  // Resubmit part
  const handleResubmitPart = async (id: string) => {
    setActionLoading(true);
    setErrorMessage("");
    try {
      await api.marketplace.resubmitPart(id);
      setSuccessMessage("Spare part resubmitted for admin review.");
      setStatusFilter("PENDING_APPROVAL");
      const data = await api.marketplace.listMyParts("PENDING_APPROVAL");
      setParts(data);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Resubmission failed.");
    } finally {
      setActionLoading(false);
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "APPROVED":
        return (
          <span className="px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" />
            <span>Approved & Live</span>
          </span>
        );
      case "PENDING_APPROVAL":
        return (
          <span className="px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            <span>Pending Approval</span>
          </span>
        );
      case "REJECTED":
        return (
          <span className="px-2.5 py-0.5 rounded-full bg-red-50 text-red-700 text-[10px] font-bold border border-red-200 flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            <span>Rejected</span>
          </span>
        );
      case "CHANGES_REQUESTED":
        return (
          <span className="px-2.5 py-0.5 rounded-full bg-orange-50 text-orange-700 text-[10px] font-bold border border-orange-200 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            <span>Changes Requested</span>
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold border border-slate-200 flex items-center gap-1">
            <FileText className="w-3 h-3" />
            <span>Draft</span>
          </span>
        );
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Messages */}
      {successMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-xs font-bold text-emerald-900 flex items-center justify-between">
          <span>{successMessage}</span>
          <button onClick={() => setSuccessMessage("")} className="text-emerald-700 hover:text-emerald-950">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-2xl text-xs font-bold text-red-900 flex items-center justify-between">
          <span>{errorMessage}</span>
          <button onClick={() => setErrorMessage("")} className="text-red-700 hover:text-red-950">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 text-white flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-xs font-bold uppercase tracking-wider border border-amber-500/20">
              Seller Inventory Management
            </span>
            <span className="text-xs text-slate-400">Moderated Submission Pipeline</span>
          </div>
          <h2 className="text-2xl font-black text-white">Dealership & Parts Inventory Dashboard</h2>
          <p className="text-xs text-slate-300 mt-1 max-w-xl">
            Submit vehicles and spare parts for marketplace compliance approval. Submissions undergo administrative verification before public publication.
          </p>
        </div>

        {/* Action Button */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          {activeSection === "vehicles" ? (
            <button
              onClick={() => {
                setErrorMessage("");
                setAddVehicleOpen(true);
              }}
              className="px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center gap-1.5"
            >
              <Plus className="w-4 h-4" />
              <span>Add Vehicle</span>
            </button>
          ) : (
            <button
              onClick={() => {
                setErrorMessage("");
                setAddPartOpen(true);
              }}
              className="px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center gap-1.5"
            >
              <Plus className="w-4 h-4" />
              <span>Add Spare Part</span>
            </button>
          )}
        </div>
      </div>

      {/* Controls & Status Filter Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-3.5 rounded-2xl border border-slate-200">
        {/* Section Switcher */}
        <div className="flex p-1 bg-slate-100 rounded-xl w-full sm:w-auto">
          <button
            onClick={() => {
              setActiveSection("vehicles");
              setStatusFilter("ALL");
            }}
            className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              activeSection === "vehicles"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            <Car className="w-3.5 h-3.5" />
            <span>My Vehicles</span>
          </button>
          <button
            onClick={() => {
              setActiveSection("parts");
              setStatusFilter("ALL");
            }}
            className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              activeSection === "parts"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            <Wrench className="w-3.5 h-3.5" />
            <span>My Spare Parts</span>
          </button>
        </div>

        {/* Status Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto text-xs pb-1 sm:pb-0">
          {["ALL", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "DRAFT"].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-xl font-bold whitespace-nowrap transition-colors ${
                statusFilter === st
                  ? "bg-slate-900 text-white"
                  : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              {st === "ALL"
                ? "All Statuses"
                : st === "PENDING_APPROVAL"
                ? "Pending"
                : st === "CHANGES_REQUESTED"
                ? "Action Req."
                : st.charAt(0) + st.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {/* =========================================================================
          SECTION 1: VEHICLES INVENTORY LIST
      ========================================================================= */}
      {activeSection === "vehicles" && (
        <div>
          {vehiclesLoading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Fetching seller vehicle stock...</p>
            </div>
          ) : vehicles.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 space-y-3">
              <Car className="w-12 h-12 text-slate-300 mx-auto" />
              <h3 className="text-base font-bold text-slate-900">No Vehicle Submissions Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                You have not submitted any vehicles under this status filter. Click below to add a vehicle to your dealership inventory.
              </p>
              <button
                onClick={() => setAddVehicleOpen(true)}
                className="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800 transition-colors inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5 text-amber-400" />
                <span>Add Vehicle Now</span>
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {vehicles.map((v) => (
                <div
                  key={v.id}
                  className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm hover:shadow-md transition-all space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      <div className="w-24 h-20 rounded-2xl bg-slate-900 overflow-hidden flex-shrink-0 flex items-center justify-center">
                        {v.primary_image_url ? (
                          <img src={v.primary_image_url} alt={v.title} className="w-full h-full object-cover" />
                        ) : (
                          <Car className="w-8 h-8 text-slate-700" />
                        )}
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-bold text-amber-600">
                            {v.year} · {v.make_name} {v.model_name}
                          </span>
                          {renderStatusBadge(v.status)}
                        </div>
                        <h4 className="text-base font-black text-slate-950">{v.title}</h4>
                        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                          <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-[10px]">
                            VIN: {v.masked_vin || "N/A"}
                          </span>
                          <span>Mileage: {v.mileage.toLocaleString()} mi</span>
                          <span>Transmission: {v.transmission}</span>
                          {v.organisation_name && (
                            <span className="flex items-center gap-1 text-slate-700 font-medium">
                              <Building2 className="w-3 h-3 text-slate-400" />
                              <span>{v.organisation_name}</span>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="text-right sm:self-center flex flex-col items-end">
                      <span className="text-xs text-slate-400">Asking Price</span>
                      <span className="text-xl font-black text-slate-950">
                        £{Number(v.price).toLocaleString()}
                      </span>
                    </div>
                  </div>

                  {/* Draft Notice & Publish Button */}
                  {v.status === "DRAFT" && (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-slate-50 border border-slate-200 rounded-2xl text-xs">
                      <div className="flex items-center gap-2 text-slate-700">
                        <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                        <span>This listing is saved as a <strong>Draft</strong>. It is not visible to buyers or sent for review until submitted.</span>
                      </div>
                      <button
                        onClick={() => handlePublishDraftVehicle(v.id)}
                        disabled={actionLoading}
                        className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50 shrink-0"
                      >
                        {actionLoading ? <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <RotateCcw className="w-3.5 h-3.5 text-amber-400" />}
                        <span>Submit For Approval</span>
                      </button>
                    </div>
                  )}

                  {/* Pending Approval Notice */}
                  {v.status === "PENDING_APPROVAL" && (
                    <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-2xl text-xs flex items-center gap-2 text-amber-900">
                      <Clock className="w-4 h-4 text-amber-600 shrink-0" />
                      <span>Submitted on {v.submitted_at ? new Date(v.submitted_at).toLocaleDateString() : "recently"}. Awaiting administrative compliance verification before public marketplace release.</span>
                    </div>
                  )}

                  {/* Approved Notice */}
                  {v.status === "APPROVED" && (
                    <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-2xl text-xs flex items-center justify-between gap-2 text-emerald-900">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                        <span>Published and actively live in the buyer marketplace!</span>
                      </div>
                      {v.reviewed_at && (
                        <span className="text-[10px] text-emerald-700">
                          Approved: {new Date(v.reviewed_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Rejection / Action Required Notice */}
                  {(v.status === "REJECTED" || v.status === "CHANGES_REQUESTED") && (
                    <div className="p-4 bg-red-50/70 border border-red-200 rounded-2xl space-y-2">
                      <div className="flex items-center justify-between text-xs font-bold text-red-900">
                        <div className="flex items-center gap-1.5">
                          <ShieldAlert className="w-4 h-4 text-red-600" />
                          <span>Compliance Reviewer Feedback</span>
                        </div>
                        <span className="text-[10px] text-red-700">
                          Reviewed: {v.reviewed_at ? new Date(v.reviewed_at).toLocaleDateString() : "Recent"}
                        </span>
                      </div>
                      <p className="text-xs text-red-800 bg-white/80 p-3 rounded-xl border border-red-100">
                        {v.rejection_reason || "Please address feedback before resubmitting."}
                      </p>
                      <div className="flex justify-end pt-1">
                        <button
                          onClick={() => handleResubmitVehicle(v.id)}
                          disabled={actionLoading}
                          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Resubmit Vehicle For Approval</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          SECTION 2: SPARE PARTS INVENTORY LIST
      ========================================================================= */}
      {activeSection === "parts" && (
        <div>
          {partsLoading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Fetching spare parts stock...</p>
            </div>
          ) : parts.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 space-y-3">
              <Wrench className="w-12 h-12 text-slate-300 mx-auto" />
              <h3 className="text-base font-bold text-slate-900">No Spare Parts Submissions Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No parts matching your current filter. Click below to add an OEM-replacement or aftermarket spare part.
              </p>
              <button
                onClick={() => setAddPartOpen(true)}
                className="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-slate-800 transition-colors inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5 text-amber-400" />
                <span>Add Spare Part Now</span>
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {parts.map((p) => (
                <div
                  key={p.id}
                  className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm hover:shadow-md transition-all space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">
                          {p.brand}
                        </span>
                        {renderStatusBadge(p.status)}
                      </div>
                      <h4 className="text-base font-black text-slate-950">{p.name}</h4>
                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-[10px]">
                          MPN: {p.mpn}
                        </span>
                        <span>Category: {p.category_name || "General"}</span>
                        <span>Stock: {p.stock_quantity} units</span>
                        <span>Condition: {p.condition}</span>
                        {p.organisation_name && (
                          <span className="flex items-center gap-1 text-slate-700 font-medium">
                            <Building2 className="w-3 h-3 text-slate-400" />
                            <span>{p.organisation_name}</span>
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="text-right sm:self-center flex flex-col items-end">
                      <span className="text-xs text-slate-400">Retail Price</span>
                      <span className="text-xl font-black text-slate-950">
                        £{Number(p.price).toFixed(2)}
                      </span>
                    </div>
                  </div>

                  {/* Draft Notice & Publish Button */}
                  {p.status === "DRAFT" && (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-slate-50 border border-slate-200 rounded-2xl text-xs">
                      <div className="flex items-center gap-2 text-slate-700">
                        <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                        <span>This spare part is saved as a <strong>Draft</strong>. It is not published or sent for review until submitted.</span>
                      </div>
                      <button
                        onClick={() => handlePublishDraftPart(p.id)}
                        disabled={actionLoading}
                        className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50 shrink-0"
                      >
                        {actionLoading ? <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <RotateCcw className="w-3.5 h-3.5 text-amber-400" />}
                        <span>Submit For Approval</span>
                      </button>
                    </div>
                  )}

                  {/* Pending Approval Notice */}
                  {p.status === "PENDING_APPROVAL" && (
                    <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-2xl text-xs flex items-center gap-2 text-amber-900">
                      <Clock className="w-4 h-4 text-amber-600 shrink-0" />
                      <span>Submitted on {p.submitted_at ? new Date(p.submitted_at).toLocaleDateString() : "recently"}. Awaiting administrative compliance review before public catalogue release.</span>
                    </div>
                  )}

                  {/* Approved Notice */}
                  {p.status === "APPROVED" && (
                    <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-2xl text-xs flex items-center justify-between gap-2 text-emerald-900">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                        <span>Published and actively live in the Parts Catalogue!</span>
                      </div>
                      {p.reviewed_at && (
                        <span className="text-[10px] text-emerald-700">
                          Approved: {new Date(p.reviewed_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Rejection notice */}
                  {(p.status === "REJECTED" || p.status === "CHANGES_REQUESTED") && (
                    <div className="p-4 bg-red-50/70 border border-red-200 rounded-2xl space-y-2">
                      <div className="flex items-center justify-between text-xs font-bold text-red-900">
                        <div className="flex items-center gap-1.5">
                          <ShieldAlert className="w-4 h-4 text-red-600" />
                          <span>Compliance Reviewer Feedback</span>
                        </div>
                        <span className="text-[10px] text-red-700">
                          Reviewed: {p.reviewed_at ? new Date(p.reviewed_at).toLocaleDateString() : "Recent"}
                        </span>
                      </div>
                      <p className="text-xs text-red-800 bg-white/80 p-3 rounded-xl border border-red-100">
                        {p.rejection_reason || "Please correct the listed issues and resubmit."}
                      </p>
                      <div className="flex justify-end pt-1">
                        <button
                          onClick={() => handleResubmitPart(p.id)}
                          disabled={actionLoading}
                          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Resubmit Part For Approval</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          MODAL: ADD VEHICLE SUBMISSION
      ========================================================================= */}
      {addVehicleOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  New Inventory Listing
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">Submit Vehicle for Marketplace Approval</h3>
              </div>
              <button
                onClick={() => setAddVehicleOpen(false)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Error Banner */}
            {vehModalError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-2xl text-xs font-bold text-red-900 flex items-center justify-between">
                <span>{vehModalError}</span>
                <button
                  type="button"
                  onClick={() => setVehModalError("")}
                  className="text-red-700 hover:text-red-950 p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1">Listing Title *</label>
                <input
                  type="text"
                  placeholder="e.g. 2021 BMW 330i M Sport Saloon"
                  value={vehTitle}
                  onChange={(e) => setVehTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Make, Model, Variant */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Make *</label>
                  <select
                    value={vehMake}
                    onChange={(e) => {
                      setVehMake(e.target.value);
                      setVehModel("");
                      setVehVariant("");
                      setModels([]);
                      setVariants([]);
                    }}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Select Make</option>
                    {makes.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-bold mb-1">Model *</label>
                  <select
                    value={vehModel}
                    onChange={(e) => {
                      setVehModel(e.target.value);
                      setVehVariant("");
                      setVariants([]);
                    }}
                    disabled={!vehMake}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500 disabled:opacity-50"
                  >
                    <option value="">Select Model</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-bold mb-1">Variant (Optional)</label>
                  <select
                    value={vehVariant}
                    onChange={(e) => setVehVariant(e.target.value)}
                    disabled={!vehModel}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500 disabled:opacity-50"
                  >
                    <option value="">Select Trim/Variant</option>
                    {variants.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} ({v.engine_code || v.fuel_type})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Price, Year, Mileage, Condition */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Asking Price (£) *</label>
                  <input
                    type="number"
                    value={vehPrice}
                    onChange={(e) => setVehPrice(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Year *</label>
                  <input
                    type="number"
                    value={vehYear}
                    onChange={(e) => setVehYear(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Mileage (mi)</label>
                  <input
                    type="number"
                    value={vehMileage}
                    onChange={(e) => setVehMileage(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Condition</label>
                  <select
                    value={vehCondition}
                    onChange={(e) => setVehCondition(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="NEW">Brand New</option>
                    <option value="EXCELLENT">Excellent</option>
                    <option value="VERY_GOOD">Very Good</option>
                    <option value="GOOD">Good</option>
                    <option value="FAIR">Fair</option>
                  </select>
                </div>
              </div>

              {/* Technical Specifications */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Fuel Type</label>
                  <select
                    value={vehFuel}
                    onChange={(e) => setVehFuel(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="PETROL">Petrol</option>
                    <option value="DIESEL">Diesel</option>
                    <option value="HYBRID">Hybrid</option>
                    <option value="EV">Electric</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Transmission</label>
                  <select
                    value={vehTrans}
                    onChange={(e) => setVehTrans(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="AUTOMATIC">Automatic</option>
                    <option value="MANUAL">Manual</option>
                    <option value="DUAL_CLUTCH">Dual Clutch</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Body Type</label>
                  <input
                    type="text"
                    placeholder="e.g. Saloon, Estate, SUV"
                    value={vehBody}
                    onChange={(e) => setVehBody(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
              </div>

              {/* Sensitive Identifiers */}
              <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 space-y-2">
                <span className="font-bold text-slate-800 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-600" />
                  <span>Identifiers (Masked for Public Privacy)</span>
                </span>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] text-slate-500 mb-0.5">Registration Plate</label>
                    <input
                      type="text"
                      placeholder="e.g. EA21 XYZ"
                      value={vehReg}
                      onChange={(e) => setVehReg(e.target.value)}
                      className="w-full px-3 py-1.5 font-mono uppercase bg-white border border-slate-200 rounded-xl focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-500 mb-0.5">Full VIN</label>
                    <input
                      type="text"
                      placeholder="17-character VIN"
                      value={vehVin}
                      onChange={(e) => setVehVin(e.target.value)}
                      className="w-full px-3 py-1.5 font-mono uppercase bg-white border border-slate-200 rounded-xl focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Dealership Organisation */}
              {userOrgs.length > 0 && (
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Listing Organisation / Dealership</label>
                  <select
                    value={vehOrg}
                    onChange={(e) => setVehOrg(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Personal Trading Account</option>
                    {userOrgs.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name} ({o.user_role})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Description & Image */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Location City</label>
                  <input
                    type="text"
                    value={vehCity}
                    onChange={(e) => setVehCity(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Location Postcode</label>
                  <input
                    type="text"
                    value={vehPostcode}
                    onChange={(e) => setVehPostcode(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Primary Image URL</label>
                  <input
                    type="url"
                    placeholder="https://..."
                    value={vehImageUrl}
                    onChange={(e) => setVehImageUrl(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Detailed Description</label>
                <textarea
                  rows={3}
                  value={vehDescription}
                  onChange={(e) => setVehDescription(e.target.value)}
                  placeholder="Service history, cosmetic notes, optional packs..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setAddVehicleOpen(false)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleSubmitVehicle(true)}
                disabled={actionLoading}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold rounded-xl transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-slate-600 border-t-transparent rounded-full animate-spin" />}
                <span>Save as Draft</span>
              </button>
              <button
                type="button"
                onClick={() => handleSubmitVehicle(false)}
                disabled={actionLoading}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Submit For Approval</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: ADD SPARE PART SUBMISSION
      ========================================================================= */}
      {addPartOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  New Spare Part Listing
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">Submit Spare Part for Marketplace Approval</h3>
              </div>
              <button
                onClick={() => setAddPartOpen(false)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Error Banner */}
            {partModalError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-2xl text-xs font-bold text-red-900 flex items-center justify-between">
                <span>{partModalError}</span>
                <button
                  type="button"
                  onClick={() => setPartModalError("")}
                  className="text-red-700 hover:text-red-950 p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1">Part Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Brembo Front Brake Discs Pair (348mm)"
                  value={partName}
                  onChange={(e) => setPartName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Brand, MPN, Category */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Brand / Manufacturer *</label>
                  <input
                    type="text"
                    placeholder="e.g. Brembo, Bosch, Mann"
                    value={partBrand}
                    onChange={(e) => setPartBrand(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">MPN (Part Number) *</label>
                  <input
                    type="text"
                    placeholder="e.g. 09.C398.13"
                    value={partMpn}
                    onChange={(e) => setPartMpn(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Taxonomy Category *</label>
                  <select
                    value={partCategory}
                    onChange={(e) => setPartCategory(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Select Category</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Price, Stock, Condition */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Price (£) *</label>
                  <input
                    type="number"
                    value={partPrice}
                    onChange={(e) => setPartPrice(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Stock Quantity</label>
                  <input
                    type="number"
                    value={partStock}
                    onChange={(e) => setPartStock(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Condition</label>
                  <select
                    value={partCondition}
                    onChange={(e) => setPartCondition(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="NEW">Brand New</option>
                    <option value="REFURBISHED">Remanufactured</option>
                    <option value="USED">Used / Tested</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">OEM Cross References (Comma-separated)</label>
                <input
                  type="text"
                  placeholder="e.g. 34116860911, 34116860912"
                  value={partOem}
                  onChange={(e) => setPartOem(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              {/* Vehicle Compatibility */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Compatible Variant (Optional)</label>
                  <select
                    value={partVariant}
                    onChange={(e) => setPartVariant(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Universal / Unlinked</option>
                    {variants.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} ({v.engine_code || v.fuel_type})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Compatibility Notes</label>
                  <input
                    type="text"
                    placeholder="e.g. Fits 330i with M-Sport Brakes only"
                    value={partCompatibilityNotes}
                    onChange={(e) => setPartCompatibilityNotes(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
              </div>

              {/* Organisation Selection */}
              {userOrgs.length > 0 && (
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Listing Organisation</label>
                  <select
                    value={partOrg}
                    onChange={(e) => setPartOrg(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Personal Trading Account</option>
                    {userOrgs.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name} ({o.user_role})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-slate-700 font-bold mb-1">Primary Image URL</label>
                <input
                  type="url"
                  placeholder="https://..."
                  value={partImageUrl}
                  onChange={(e) => setPartImageUrl(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Technical Description</label>
                <textarea
                  rows={3}
                  value={partDescription}
                  onChange={(e) => setPartDescription(e.target.value)}
                  placeholder="Material specs, coating, packaging notes..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setAddPartOpen(false)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleSubmitPart(true)}
                disabled={actionLoading}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold rounded-xl transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-slate-600 border-t-transparent rounded-full animate-spin" />}
                <span>Save as Draft</span>
              </button>
              <button
                type="button"
                onClick={() => handleSubmitPart(false)}
                disabled={actionLoading}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Submit For Approval</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
