"use client";

import React, { useState, useEffect, useCallback } from "react";
import { api, GarageVehicle, AddGarageVehiclePayload, VehicleMake, VehicleModel, VehicleVariant, ApiError } from "@/lib/api/client";
import {
  Car,
  Plus,
  Star,
  Trash2,
  Edit2,
  Gauge,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  X,
  Fuel,
} from "lucide-react";

interface Phase2GarageViewProps {
  initialVehicleId?: string;
}

export default function Phase2GarageView({ initialVehicleId }: Phase2GarageViewProps = {}) {
  const [vehicles, setVehicles] = useState<GarageVehicle[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<GarageVehicle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [vehicleToDelete, setVehicleToDelete] = useState<GarageVehicle | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Add vehicle mode: "catalogue" or "manual"
  const [addMode, setAddMode] = useState<"catalogue" | "manual">("catalogue");

  // Catalogue cascading select states
  const [makes, setMakes] = useState<VehicleMake[]>([]);
  const [models, setModels] = useState<VehicleModel[]>([]);
  const [variants, setVariants] = useState<VehicleVariant[]>([]);
  const [selectedMakeId, setSelectedMakeId] = useState("");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [selectedVariantId, setSelectedVariantId] = useState("");

  // Common Add Form fields
  const [formPlate, setFormPlate] = useState("");
  const [formVin, setFormVin] = useState("");
  const [formNickname, setFormNickname] = useState("");
  const [formOdometer, setFormOdometer] = useState<number | "">("");
  const [formColor, setFormColor] = useState("");

  // Manual Add Form fields
  const [formManualMake, setFormManualMake] = useState("");
  const [formManualModel, setFormManualModel] = useState("");
  const [formManualYear, setFormManualYear] = useState<number | "">(new Date().getFullYear());
  const [formManualTrim, setFormManualTrim] = useState("");
  const [formManualFuel, setFormManualFuel] = useState("PETROL");
  const [formManualTransmission, setFormManualTransmission] = useState("MANUAL");

  // Edit Form fields
  const [editPlate, setEditPlate] = useState("");
  const [editNickname, setEditNickname] = useState("");
  const [editOdometer, setEditOdometer] = useState<number | "">("");
  const [editColor, setEditColor] = useState("");

  const showSuccess = (msg: string) => {
    setActionSuccess(msg);
    setTimeout(() => setActionSuccess(null), 4000);
  };

  const loadVehicles = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMsg(null);
      const data = await api.garage.listVehicles();
      setVehicles(data);
      if (data.length > 0) {
        setSelectedVehicle((prev) => {
          if (!prev) return data[0];
          const found = data.find((v) => v.id === prev.id);
          return found || data[0];
        });
      } else {
        setSelectedVehicle(null);
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to load garage vehicles. Please refresh or try again.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    api.garage.listVehicles()
      .then((data) => {
        if (!ignore) {
          setVehicles(data);
          if (data.length > 0) setSelectedVehicle(data[0]);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setErrorMsg(err instanceof ApiError ? err.message : "Failed to load garage vehicles. Please refresh or try again.");
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  // Handle external navigation (from Global Search) to a specific garage vehicle
  useEffect(() => {
    if (!initialVehicleId || vehicles.length === 0) return;
    const match = vehicles.find((v) => v.id === initialVehicleId);
    if (match) {
      const timer = setTimeout(() => {
        setSelectedVehicle(match);
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [initialVehicleId, vehicles]);

  // Load makes when add modal opens
  useEffect(() => {
    if (!isAddModalOpen || makes.length > 0) return;
    let ignore = false;
    api.catalogue.getMakes().then((res) => {
      if (!ignore) setMakes(res);
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, [isAddModalOpen, makes.length]);

  // Cascading models
  useEffect(() => {
    if (!selectedMakeId) return;
    let ignore = false;
    api.catalogue.getModels(selectedMakeId).then((res) => {
      if (!ignore) setModels(res);
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, [selectedMakeId]);

  // Cascading variants
  useEffect(() => {
    if (!selectedModelId) return;
    let ignore = false;
    api.catalogue.getVariants(selectedModelId).then((res) => {
      if (!ignore) setVariants(res);
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, [selectedModelId]);

  const handleSetPrimary = async (vehicleId: string) => {
    try {
      setErrorMsg(null);
      await api.garage.setPrimary(vehicleId);
      showSuccess("Primary vehicle updated successfully.");
      await loadVehicles();
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to set primary vehicle.");
    }
  };

  const handleArchiveVehicle = async () => {
    if (!vehicleToDelete) return;
    try {
      setIsSubmitting(true);
      setErrorMsg(null);
      await api.garage.archiveVehicle(vehicleToDelete.id);
      showSuccess(`Vehicle ${vehicleToDelete.year} ${vehicleToDelete.make} ${vehicleToDelete.model} archived.`);
      setVehicleToDelete(null);
      await loadVehicles();
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to archive vehicle.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAddVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      const payload: AddGarageVehiclePayload = {
        registration_plate: formPlate.trim().toUpperCase() || undefined,
        vin: formVin.trim().toUpperCase() || undefined,
        nickname: formNickname.trim() || undefined,
        color: formColor.trim() || undefined,
        current_odometer: formOdometer === "" ? undefined : Number(formOdometer),
      };

      if (addMode === "catalogue") {
        if (!selectedVariantId) {
          setErrorMsg("Please select a vehicle variant from the catalogue.");
          setIsSubmitting(false);
          return;
        }
        payload.vehicle_variant = selectedVariantId;
      } else {
        if (!formManualMake.trim() || !formManualModel.trim() || !formManualYear) {
          setErrorMsg("Make, model, and year are required for manual vehicle entry.");
          setIsSubmitting(false);
          return;
        }
        payload.make = formManualMake.trim();
        payload.model = formManualModel.trim();
        payload.year = Number(formManualYear);
        payload.trim = formManualTrim.trim() || undefined;
        payload.fuel_type = formManualFuel;
        payload.transmission = formManualTransmission;
      }

      const created = await api.garage.addVehicle(payload);
      showSuccess(`Vehicle ${created.year} ${created.make} ${created.model} added to your garage.`);
      setIsAddModalOpen(false);
      resetAddForm();
      await loadVehicles();
      setSelectedVehicle(created);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to add vehicle.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVehicle) return;
    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      const updated = await api.garage.updateVehicle(selectedVehicle.id, {
        registration_plate: editPlate.trim().toUpperCase() || undefined,
        nickname: editNickname.trim() || undefined,
        color: editColor.trim() || undefined,
        current_odometer: editOdometer === "" ? undefined : Number(editOdometer),
      });
      showSuccess(`Vehicle ${updated.make} ${updated.model} details updated.`);
      setIsEditModalOpen(false);
      await loadVehicles();
      setSelectedVehicle(updated);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to update vehicle.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const openEditModal = (vehicle: GarageVehicle) => {
    setSelectedVehicle(vehicle);
    setEditPlate(vehicle.registration_plate || "");
    setEditNickname(vehicle.nickname || "");
    setEditOdometer(vehicle.current_odometer ?? "");
    setEditColor(vehicle.color || "");
    setIsEditModalOpen(true);
  };

  const resetAddForm = () => {
    setSelectedMakeId("");
    setSelectedModelId("");
    setSelectedVariantId("");
    setFormPlate("");
    setFormVin("");
    setFormNickname("");
    setFormOdometer("");
    setFormColor("");
    setFormManualMake("");
    setFormManualModel("");
    setFormManualYear(new Date().getFullYear());
    setFormManualTrim("");
  };

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-amber-400 text-slate-950 font-black text-xs">
              Garage
            </span>
            <h1 className="text-xl font-black text-slate-950">My Personal Garage</h1>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Store and manage your vehicles to enable confirmed parts fitment and specification tracking.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadVehicles()}
            disabled={isLoading}
            className="p-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 transition-colors"
            title="Refresh Garage Vehicles"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin text-amber-500" : ""}`} />
          </button>
          <button
            onClick={() => {
              resetAddForm();
              setIsAddModalOpen(true);
            }}
            className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold px-4 py-2.5 rounded-xl text-xs flex items-center gap-2 shadow-sm transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Add Vehicle</span>
          </button>
        </div>
      </div>

      {/* Notifications */}
      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center gap-2 shadow-sm">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Content layout */}
      {isLoading && vehicles.length === 0 ? (
        <div className="p-16 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
          <div className="w-8 h-8 border-3 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-xs font-bold text-slate-700">Loading your personal garage...</p>
        </div>
      ) : vehicles.length === 0 ? (
        <div className="p-16 bg-white rounded-2xl border border-slate-200 text-center space-y-4">
          <div className="w-14 h-14 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center mx-auto border border-amber-200">
            <Car className="w-7 h-7" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-950">Your Garage is Empty</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
              Add your vehicle from the verified catalogue or register it manually. Once added, DriverXtra will automatically evaluate part fitment and maintenance requirements.
            </p>
          </div>
          <button
            onClick={() => {
              resetAddForm();
              setIsAddModalOpen(true);
            }}
            className="bg-slate-950 hover:bg-slate-800 text-white font-bold px-5 py-2.5 rounded-xl text-xs inline-flex items-center gap-2 shadow-sm transition-all"
          >
            <Plus className="w-4 h-4 text-amber-400" />
            <span>Add Your First Vehicle</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Vehicle List (Left 2 cols on lg) */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between text-xs font-bold text-slate-600 px-1">
              <span>{vehicles.length} {vehicles.length === 1 ? "Vehicle" : "Vehicles"} Registered</span>
              <span className="text-[11px] font-normal text-slate-500">Registered Vehicles</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {vehicles.map((veh) => {
                const isSelected = selectedVehicle?.id === veh.id;
                return (
                  <div
                    key={veh.id}
                    onClick={() => setSelectedVehicle(veh)}
                    className={`cursor-pointer bg-white rounded-2xl p-5 border transition-all relative overflow-hidden flex flex-col justify-between ${
                      isSelected
                        ? "border-amber-400 ring-2 ring-amber-400/20 shadow-md"
                        : "border-slate-200 hover:border-slate-300 shadow-sm"
                    }`}
                  >
                    <div>
                      {/* Top badges */}
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <div className="flex items-center gap-1.5">
                          {veh.is_primary && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-100 text-amber-900 border border-amber-300">
                              <Star className="w-3 h-3 fill-amber-500 text-amber-500" />
                              Primary Vehicle
                            </span>
                          )}
                          {veh.vehicle_variant && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                              Catalogue Verified
                            </span>
                          )}
                        </div>

                        {veh.registration_plate ? (
                          <span className="px-2.5 py-1 rounded-md bg-amber-400 text-slate-950 font-black text-xs tracking-wider border border-amber-500 font-mono shadow-sm">
                            {veh.registration_plate}
                          </span>
                        ) : (
                          <span className="text-[10px] text-slate-400 font-mono">NO PLATE</span>
                        )}
                      </div>

                      {/* Make & Model */}
                      <h3 className="text-base font-black text-slate-950 truncate">
                        {veh.year} {veh.make} {veh.model}
                      </h3>
                      {veh.trim && (
                        <p className="text-xs font-semibold text-slate-600 truncate mt-0.5">
                          {veh.trim}
                        </p>
                      )}
                      {veh.nickname && (
                        <p className="text-[11px] italic text-slate-500 mt-1">
                          &ldquo;{veh.nickname}&rdquo;
                        </p>
                      )}

                      {/* Technical Specs Pills */}
                      <div className="grid grid-cols-2 gap-2 mt-4 pt-3 border-t border-slate-100 text-slate-600 text-xs">
                        <div className="flex items-center gap-1.5">
                          <Gauge className="w-3.5 h-3.5 text-slate-400" />
                          <span className="font-semibold text-slate-800">
                            {veh.current_odometer ? `${veh.current_odometer.toLocaleString()} ${veh.odometer_unit}` : "Odo Unset"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Fuel className="w-3.5 h-3.5 text-slate-400" />
                          <span className="font-semibold text-slate-800 uppercase text-[11px]">
                            {veh.fuel_type || "Petrol"}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Bottom Card Actions */}
                    <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                      {!veh.is_primary ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSetPrimary(veh.id);
                          }}
                          className="text-amber-600 hover:text-amber-700 font-bold text-[11px] flex items-center gap-1"
                        >
                          <Star className="w-3 h-3" />
                          Set Primary
                        </button>
                      ) : (
                        <span className="text-[11px] font-bold text-emerald-600 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          Active Primary
                        </span>
                      )}

                      <div className="flex items-center gap-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            openEditModal(veh);
                          }}
                          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 transition-colors"
                          title="Edit vehicle details"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setVehicleToDelete(veh);
                          }}
                          className="p-1.5 rounded-lg hover:bg-amber-50 text-amber-600 transition-colors"
                          title="Archive vehicle"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Vehicle Inspector (Right 1 col on lg) */}
          <div className="space-y-4">
            {selectedVehicle ? (
              <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-5 sticky top-6">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div>
                    <span className="text-[10px] font-black uppercase tracking-wider text-amber-500">
                      Vehicle Master Record
                    </span>
                    <h3 className="text-base font-black text-slate-950">
                      {selectedVehicle.year} {selectedVehicle.make} {selectedVehicle.model}
                    </h3>
                  </div>
                  {selectedVehicle.is_primary && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-amber-400 text-slate-950">
                      PRIMARY
                    </span>
                  )}
                </div>

                {/* Details Breakdown */}
                <div className="space-y-3 text-xs">
                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <span className="text-slate-500">Registration Plate</span>
                    <span className="font-mono font-bold text-slate-950 bg-slate-100 px-2 py-0.5 rounded">
                      {selectedVehicle.registration_plate || "N/A"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <div className="flex flex-col">
                      <span className="text-slate-500">VIN</span>
                      <span className="text-[10px] text-slate-400">Masked for privacy</span>
                    </div>
                    <span className="font-mono font-bold text-slate-950 text-[11px]">
                      {selectedVehicle.vin || "Not recorded"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <span className="text-slate-500">Trim / Specification</span>
                    <span className="font-bold text-slate-800 truncate max-w-[180px]">
                      {selectedVehicle.trim || "Standard"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <span className="text-slate-500">Engine Code</span>
                    <span className="font-mono font-bold text-slate-800">
                      {selectedVehicle.engine_code || "Unknown"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <span className="text-slate-500">Power Rating</span>
                    <span className="font-bold text-slate-800">
                      {selectedVehicle.power_bhp ? `${selectedVehicle.power_bhp} bhp` : "N/A"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <span className="text-slate-500">Fuel & Transmission</span>
                    <span className="font-bold text-slate-800 uppercase text-[11px]">
                      {selectedVehicle.fuel_type || "Petrol"} • {selectedVehicle.transmission || "Manual"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <span className="text-slate-500">Odometer</span>
                    <span className="font-bold text-slate-800">
                      {selectedVehicle.current_odometer ? `${selectedVehicle.current_odometer.toLocaleString()} ${selectedVehicle.odometer_unit}` : "Unset"}
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-50">
                    <div className="flex flex-col">
                      <span className="text-slate-500">MOT Status</span>
                      <span className="text-[10px] text-amber-600 font-medium">UK · Self-reported</span>
                    </div>
                    <span className={`font-bold px-2 py-0.5 rounded text-[10px] uppercase ${
                      selectedVehicle.mot_status === "VALID" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"
                    }`}>
                      {selectedVehicle.mot_status} (Self-reported)
                    </span>
                  </div>

                  <div className="flex justify-between py-1.5">
                    <div className="flex flex-col">
                      <span className="text-slate-500">Active Recalls</span>
                      <span className="text-[10px] text-amber-600 font-medium">Self-reported</span>
                    </div>
                    <span className="font-bold text-slate-800 text-xs">
                      {selectedVehicle.active_recalls_count} pending
                    </span>
                  </div>
                </div>

                {/* Actions */}
                <div className="pt-3 border-t border-slate-100 space-y-2">
                  <button
                    onClick={() => openEditModal(selectedVehicle)}
                    className="w-full bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 transition-colors"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                    <span>Update Vehicle Information</span>
                  </button>

                  {!selectedVehicle.is_primary && (
                    <button
                      onClick={() => handleSetPrimary(selectedVehicle.id)}
                      className="w-full bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-300 font-bold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 transition-colors"
                    >
                      <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                      <span>Designate as Primary Vehicle</span>
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-xs text-slate-500">
                Select a vehicle to inspect full telemetry and specifications.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ==================================================== */}
      {/* Modal: Add Vehicle                                  */}
      {/* ==================================================== */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-amber-400 text-slate-950 flex items-center justify-center font-bold">
                  <Car className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-black text-slate-950">Add Vehicle to Garage</h3>
                  <p className="text-[11px] text-slate-500">Verified Vehicle Registry</p>
                </div>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Mode Switcher Tabs */}
            <div className="grid grid-cols-2 p-1 bg-slate-100 rounded-xl">
              <button
                type="button"
                onClick={() => setAddMode("catalogue")}
                className={`py-2 text-xs font-bold rounded-lg transition-all ${
                  addMode === "catalogue"
                    ? "bg-white text-slate-950 shadow-sm"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                Select from Catalogue
              </button>
              <button
                type="button"
                onClick={() => setAddMode("manual")}
                className={`py-2 text-xs font-bold rounded-lg transition-all ${
                  addMode === "manual"
                    ? "bg-white text-slate-950 shadow-sm"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                Enter Details Manually
              </button>
            </div>

            <form onSubmit={handleAddVehicle} className="space-y-4">
              {addMode === "catalogue" ? (
                /* Catalogue Cascading Selects */
                <div className="space-y-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-amber-600">
                    Step 1: Canonical Vehicle Hierarchy
                  </span>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Vehicle Make *</label>
                    <select
                      value={selectedMakeId}
                      onChange={(e) => setSelectedMakeId(e.target.value)}
                      className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white font-medium focus:outline-none focus:ring-2 focus:ring-amber-400"
                    >
                      <option value="">-- Choose Make --</option>
                      {makes.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Vehicle Model *</label>
                    <select
                      value={selectedModelId}
                      onChange={(e) => setSelectedModelId(e.target.value)}
                      disabled={!selectedMakeId}
                      className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white font-medium focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100 disabled:text-slate-400"
                    >
                      <option value="">-- Choose Model --</option>
                      {models.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name} ({m.year_start} - {m.year_end || "Present"})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Trim / Engine Variant *</label>
                    <select
                      value={selectedVariantId}
                      onChange={(e) => setSelectedVariantId(e.target.value)}
                      disabled={!selectedModelId}
                      className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white font-medium focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100 disabled:text-slate-400"
                    >
                      <option value="">-- Choose Variant --</option>
                      {variants.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.year} {v.name} ({v.fuel_type}, {v.transmission}, {v.power_bhp ? `${v.power_bhp}bhp` : ""})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : (
                /* Manual Entry Form */
                <div className="space-y-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-amber-600">
                    Step 1: Custom Vehicle Information
                  </span>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Make *</label>
                      <input
                        type="text"
                        placeholder="e.g. Audi"
                        value={formManualMake}
                        onChange={(e) => setFormManualMake(e.target.value)}
                        required
                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Model *</label>
                      <input
                        type="text"
                        placeholder="e.g. A3 Sportback"
                        value={formManualModel}
                        onChange={(e) => setFormManualModel(e.target.value)}
                        required
                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Model Year *</label>
                      <input
                        type="number"
                        min="1950"
                        max="2030"
                        value={formManualYear}
                        onChange={(e) => setFormManualYear(e.target.value === "" ? "" : Number(e.target.value))}
                        required
                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Trim / Specification</label>
                      <input
                        type="text"
                        placeholder="e.g. S Line"
                        value={formManualTrim}
                        onChange={(e) => setFormManualTrim(e.target.value)}
                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Fuel Type</label>
                      <select
                        value={formManualFuel}
                        onChange={(e) => setFormManualFuel(e.target.value)}
                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                      >
                        <option value="PETROL">Petrol</option>
                        <option value="DIESEL">Diesel</option>
                        <option value="HYBRID">Hybrid</option>
                        <option value="ELECTRIC">Electric</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Transmission</label>
                      <select
                        value={formManualTransmission}
                        onChange={(e) => setFormManualTransmission(e.target.value)}
                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                      >
                        <option value="MANUAL">Manual</option>
                        <option value="AUTOMATIC">Automatic</option>
                        <option value="DUAL_CLUTCH">Dual Clutch (DCT)</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              {/* Step 2: Personal Vehicle Identifiers */}
              <div className="space-y-3 pt-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Step 2: Identification & Usage (Optional)
                </span>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Registration Plate</label>
                    <input
                      type="text"
                      placeholder="e.g. GF21 XTR"
                      value={formPlate}
                      onChange={(e) => setFormPlate(e.target.value)}
                      className="w-full px-3 py-2 text-xs font-mono font-bold uppercase rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">VIN (17 characters)</label>
                    <input
                      type="text"
                      placeholder="e.g. WBA5R1C50M8219420"
                      maxLength={17}
                      value={formVin}
                      onChange={(e) => setFormVin(e.target.value)}
                      className="w-full px-3 py-2 text-xs font-mono uppercase rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Odometer (mi)</label>
                    <input
                      type="number"
                      placeholder="34000"
                      value={formOdometer}
                      onChange={(e) => setFormOdometer(e.target.value === "" ? "" : Number(e.target.value))}
                      className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Color</label>
                    <input
                      type="text"
                      placeholder="e.g. Alpine White"
                      value={formColor}
                      onChange={(e) => setFormColor(e.target.value)}
                      className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Nickname</label>
                    <input
                      type="text"
                      placeholder="e.g. Daily Commuter"
                      value={formNickname}
                      onChange={(e) => setFormNickname(e.target.value)}
                      className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>
                </div>
              </div>

              {/* Submit Buttons */}
              <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold px-5 py-2.5 rounded-xl text-xs flex items-center gap-2 shadow-sm transition-all disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Saving Vehicle...</span>
                    </>
                  ) : (
                    <>
                      <Plus className="w-3.5 h-3.5" />
                      <span>Confirm & Save</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================== */}
      {/* Modal: Edit Vehicle                                 */}
      {/* ==================================================== */}
      {isEditModalOpen && selectedVehicle && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-slate-950">Update Vehicle Information</h3>
                <p className="text-[11px] text-slate-500">
                  {selectedVehicle.year} {selectedVehicle.make} {selectedVehicle.model}
                </p>
              </div>
              <button
                onClick={() => setIsEditModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleEditVehicle} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Registration Plate</label>
                <input
                  type="text"
                  value={editPlate}
                  onChange={(e) => setEditPlate(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono font-bold uppercase rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Nickname</label>
                <input
                  type="text"
                  value={editNickname}
                  onChange={(e) => setEditNickname(e.target.value)}
                  placeholder="e.g. Project Car"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Odometer (mi)</label>
                  <input
                    type="number"
                    value={editOdometer}
                    onChange={(e) => setEditOdometer(e.target.value === "" ? "" : Number(e.target.value))}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Color</label>
                  <input
                    type="text"
                    value={editColor}
                    onChange={(e) => setEditColor(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-slate-950 hover:bg-slate-800 text-white font-bold px-5 py-2.5 rounded-xl text-xs flex items-center gap-2 shadow-sm transition-all disabled:opacity-50"
                >
                  {isSubmitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================== */}
      {/* Modal: Archive Confirmation                         */}
      {/* ==================================================== */}
      {vehicleToDelete && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-sm w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center mx-auto">
              <Trash2 className="w-5 h-5" />
            </div>
            <div className="text-center">
              <h3 className="text-base font-black text-slate-950">Archive Vehicle</h3>
              <p className="text-xs text-slate-500 mt-1">
                Are you sure you want to archive <span className="font-bold text-slate-800">{vehicleToDelete.year} {vehicleToDelete.make} {vehicleToDelete.model}</span> ({vehicleToDelete.registration_plate || "No plate"})? It will be removed from your active garage, while preserving historical fitment and order records.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => setVehicleToDelete(null)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleArchiveVehicle}
                disabled={isSubmitting}
                className="bg-amber-600 hover:bg-amber-700 text-white font-bold px-4 py-2 rounded-xl text-xs transition-colors shadow-sm disabled:opacity-50"
              >
                {isSubmitting ? "Archiving..." : "Archive Vehicle"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
