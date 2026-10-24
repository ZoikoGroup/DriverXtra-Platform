"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  api,
  resolveMediaUrl,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  VehicleMake,
  VehicleModel,
  VehicleVariant,
  PartCategory,
  PartSummary,
  BackendOrganisation,
  CreateVehicleListingPayload,
  CreatePartListingPayload,
  StockMovement,
  PriceChange,
  VehicleCatalogueApplication,
  CreateVehicleCatalogueApplicationPayload,
  CataloguePhotoProposal,
  HsnClassificationOption,
  VehicleEnquiry,
  VehicleEnquiryStatus,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import ListingPhotoManager from "./ListingPhotoManager";
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
  Pencil,
  Sliders,
  History,
  FilePlus,
  Camera,
  ExternalLink,
  HelpCircle,
  Upload,
  Loader2,
  MessageSquare,
  Phone,
  Mail,
  MessageCircle,
  Send,
  Check,
  Lock,
} from "lucide-react";

export default function SellerInventoryView() {
  const { user } = useAuth();
  const [activeSection, setActiveSection] = useState<"vehicles" | "parts" | "applications" | "enquiries">("vehicles");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  // Vehicle Enquiries state
  const [enquiries, setEnquiries] = useState<VehicleEnquiry[]>([]);
  const [enquiriesLoading, setEnquiriesLoading] = useState(false);
  const [enquiryStatusFilter, setEnquiryStatusFilter] = useState<string>("ALL");
  const [updatingEnquiryId, setUpdatingEnquiryId] = useState<string | null>(null);
  const [sellerNotesDraft, setSellerNotesDraft] = useState<Record<string, string>>({});
  const [savingNoteId, setSavingNoteId] = useState<string | null>(null);
  const [sellerReplyDraft, setSellerReplyDraft] = useState<Record<string, string>>({});
  const [replyingEnquiryId, setReplyingEnquiryId] = useState<string | null>(null);
  const [replySuccessId, setReplySuccessId] = useState<string | null>(null);
  const [replyError, setReplyError] = useState<Record<string, string>>({});

  // Vehicles state
  const [vehicles, setVehicles] = useState<MarketplaceVehicleListing[]>([]);
  const [vehiclesLoading, setVehiclesLoading] = useState(false);
  const [addVehicleOpen, setAddVehicleOpen] = useState(false);

  // Parts state
  const [parts, setParts] = useState<MarketplacePartListing[]>([]);
  const [partsLoading, setPartsLoading] = useState(false);
  const [addPartOpen, setAddPartOpen] = useState(false);

  // Edit Vehicle State
  const [editingVehicle, setEditingVehicle] = useState<MarketplaceVehicleListing | null>(null);
  const [editVehPrice, setEditVehPrice] = useState("");
  const [editVehMileage, setEditVehMileage] = useState("");
  const [editVehDescription, setEditVehDescription] = useState("");
  const [editVehPrimaryImageUrl, setEditVehPrimaryImageUrl] = useState("");
  const [editVehImages, setEditVehImages] = useState<string[]>([]);

  // Edit Part State (Phase 3 Part B: price, compare-at, catalogue part)
  const [editingPart, setEditingPart] = useState<MarketplacePartListing | null>(null);
  const [editPartPrice, setEditPartPrice] = useState("");
  const [editPartCompareAtPrice, setEditPartCompareAtPrice] = useState("");
  const [editPartCataloguePart, setEditPartCataloguePart] = useState("");
  const [editPartDescription, setEditPartDescription] = useState("");
  const [editPartVariant, setEditPartVariant] = useState("");
  const [editPartCompatibilityNotes, setEditPartCompatibilityNotes] = useState("");
  const [editPartPrimaryImageUrl, setEditPartPrimaryImageUrl] = useState("");
  const [editPartImages, setEditPartImages] = useState<string[]>([]);
  const [editPartHsnCode, setEditPartHsnCode] = useState<string>("8708");
  const [editPartGstRate, setEditPartGstRate] = useState<string>("28.00");

  // Stock Adjust State (Phase 3 Part A)
  const [adjustingPart, setAdjustingPart] = useState<MarketplacePartListing | null>(null);
  const [adjustDelta, setAdjustDelta] = useState<string>("");
  const [adjustReason, setAdjustReason] = useState<"ADJUSTMENT" | "CORRECTION">("ADJUSTMENT");
  const [adjustNote, setAdjustNote] = useState<string>("");
  const [adjustModalError, setAdjustModalError] = useState<string>("");

  // Stock History State (Phase 3 Part A)
  const [historyPart, setHistoryPart] = useState<MarketplacePartListing | null>(null);
  const [stockMovements, setStockMovements] = useState<StockMovement[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);

  // Price History State (Phase 3 Part B)
  const [priceHistoryPart, setPriceHistoryPart] = useState<MarketplacePartListing | null>(null);
  const [priceChanges, setPriceChanges] = useState<PriceChange[]>([]);
  const [priceHistoryLoading, setPriceHistoryLoading] = useState<boolean>(false);

  // Reference data
  const [makes, setMakes] = useState<VehicleMake[]>([]);
  const [models, setModels] = useState<VehicleModel[]>([]);
  const [variants, setVariants] = useState<VehicleVariant[]>([]);
  const [categories, setCategories] = useState<PartCategory[]>([]);
  const [catalogueParts, setCatalogueParts] = useState<PartSummary[]>([]);
  const [userOrgs, setUserOrgs] = useState<BackendOrganisation[]>([]);

  // Helpers for Org Roles and Permissions (Phase 4)
  const parseConflictDetails = (err: unknown): {
    message: string;
    conflicts?: Array<{ variant_id?: string; display_name?: string; qualifications?: string }>;
  } => {
    if (err && typeof err === "object") {
      const apiErr = err as { message?: string; details?: Record<string, unknown> };
      const details = apiErr.details;
      if (details && typeof details === "object" && Array.isArray(details.conflicts)) {
        return {
          message: apiErr.message || "Listing cannot be submitted with conflicting vehicle fitments.",
          conflicts: details.conflicts as Array<{ variant_id?: string; display_name?: string; qualifications?: string }>,
        };
      }
    }
    const msg = err instanceof Error ? err.message : "An error occurred";
    return { message: msg };
  };

  const canManageListing = (item: { organisation?: string | null; seller?: string }) => {
    if (user?.is_superuser || user?.rawRoles?.includes("ADMIN") || user?.role === "MARKETPLACE_ADMIN") return true;
    if (item.organisation) {
      const org = userOrgs.find((o) => o.id === item.organisation);
      return org?.user_role === "OWNER" || org?.user_role === "ADMIN";
    }
    return item.seller === user?.id || !item.seller;
  };

  const canResubmitListing = (item: { organisation?: string | null; seller?: string }) => {
    if (user?.is_superuser || user?.rawRoles?.includes("ADMIN") || user?.role === "MARKETPLACE_ADMIN") return true;
    if (item.seller === user?.id) return true;
    if (item.organisation) {
      const org = userOrgs.find((o) => o.id === item.organisation);
      return org?.user_role === "OWNER" || org?.user_role === "ADMIN";
    }
    return true;
  };

  // Feedback states
  const [actionLoading, setActionLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [vehModalError, setVehModalError] = useState("");
  const [partModalError, setPartModalError] = useState("");

  // Conflict modal state for clear blocking message (Phase 3 Part C)
  const [conflictModal, setConflictModal] = useState<{
    title: string;
    message: string;
    conflicts?: Array<{ variant_id?: string; display_name?: string; qualifications?: string }>;
  } | null>(null);

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
  const [vehPrimaryImageUrl, setVehPrimaryImageUrl] = useState("");
  const [vehImages, setVehImages] = useState<string[]>([]);
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
  const [partCompareAtPrice, setPartCompareAtPrice] = useState("");
  const [partCataloguePart, setPartCataloguePart] = useState("");
  const [partStock, setPartStock] = useState("5");
  const [partCondition, setPartCondition] = useState("NEW");
  const [partDescription, setPartDescription] = useState("");
  const [partPrimaryImageUrl, setPartPrimaryImageUrl] = useState("");
  const [partImages, setPartImages] = useState<string[]>([]);
  const [partVariant, setPartVariant] = useState("");
  const [partCompatibilityNotes, setPartCompatibilityNotes] = useState("");
  const [partOrg, setPartOrg] = useState("");
  const [partHsnCode, setPartHsnCode] = useState<string>("8708");
  const [partGstRate, setPartGstRate] = useState<string>("28.00");
  const [hsnOptions, setHsnOptions] = useState<HsnClassificationOption[]>([]);

  // Catalogue Application State
  const [appModalOpen, setAppModalOpen] = useState(false);
  const [myApplications, setMyApplications] = useState<VehicleCatalogueApplication[]>([]);
  const [applicationsLoading, setApplicationsLoading] = useState(false);
  const [appMakeMode, setAppMakeMode] = useState<"SELECT" | "CUSTOM">("SELECT");
  const [appMakeId, setAppMakeId] = useState("");
  const [appMakeName, setAppMakeName] = useState("");
  const [appModelName, setAppModelName] = useState("");
  const [appYearStart, setAppYearStart] = useState("2020");
  const [appYearEnd, setAppYearEnd] = useState("");
  const [appVariantName, setAppVariantName] = useState("");
  const [appYear, setAppYear] = useState("2021");
  const [appFuel, setAppFuel] = useState("PETROL");
  const [appTrans, setAppTrans] = useState("AUTOMATIC");
  const [appBody, setAppBody] = useState("Saloon");
  const [appEngineCode, setAppEngineCode] = useState("");
  const [appPowerBhp, setAppPowerBhp] = useState("");
  const [appEngineCapacityCc, setAppEngineCapacityCc] = useState("");
  const [appPrimaryImageUrl, setAppPrimaryImageUrl] = useState("");
  const [appImages, setAppImages] = useState<string[]>([]);
  const [appNotes, setAppNotes] = useState("");
  const [appModalError, setAppModalError] = useState("");
  const [appSubmitting, setAppSubmitting] = useState(false);

  // Catalogue Photo Proposal State
  const [photoProposalOpen, setPhotoProposalOpen] = useState(false);
  const [proposalModelId, setProposalModelId] = useState("");
  const [proposalModelName, setProposalModelName] = useState("");
  const [proposalMakeName, setProposalMakeName] = useState("");
  const [proposalCurrentUrl, setProposalCurrentUrl] = useState("");
  const [proposedUrl, setProposedUrl] = useState("");
  const [proposalNotes, setProposalNotes] = useState("");
  const [proposalError, setProposalError] = useState("");
  const [proposalLoading, setProposalLoading] = useState(false);
  const [proposalUploading, setProposalUploading] = useState(false);
  const proposalFileInputRef = useRef<HTMLInputElement | null>(null);
  const [myPhotoProposals, setMyPhotoProposals] = useState<CataloguePhotoProposal[]>([]);

  const handleProposalFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    e.target.value = "";
    setProposalError("");
    setProposalUploading(true);
    try {
      const res = await api.marketplace.uploadImage(file, { listingType: "catalogue" });
      setProposedUrl(res.url);
    } catch (err: unknown) {
      setProposalError(err instanceof Error ? err.message : "Failed to upload photo.");
    } finally {
      setProposalUploading(false);
    }
  };

  const resetVehicleForm = () => {
    setVehTitle("");
    setVehMake("");
    setVehModel("");
    setVehVariant("");
    setModels([]);
    api.catalogue.getVariants().then(setVariants).catch(console.error);
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
    setVehPrimaryImageUrl("");
    setVehImages([]);
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
    setPartCompareAtPrice("");
    setPartCataloguePart("");
    setPartStock("5");
    setPartCondition("NEW");
    setPartDescription("");
    setPartPrimaryImageUrl("");
    setPartImages([]);
    setPartVariant("");
    setPartCompatibilityNotes("");
    setPartHsnCode("8708");
    setPartGstRate("28.00");
    setPartModalError("");
  };

  const resetApplicationForm = () => {
    setAppMakeMode("SELECT");
    setAppMakeId("");
    setAppMakeName("");
    setAppModelName("");
    setAppYearStart("2020");
    setAppYearEnd("");
    setAppVariantName("");
    setAppYear("2021");
    setAppFuel("PETROL");
    setAppTrans("AUTOMATIC");
    setAppBody("Saloon");
    setAppEngineCode("");
    setAppPowerBhp("");
    setAppEngineCapacityCc("");
    setAppPrimaryImageUrl("");
    setAppImages([]);
    setAppNotes("");
    setAppModalError("");
  };

  const loadMyApplications = async () => {
    setApplicationsLoading(true);
    try {
      const data = await api.catalogue.listApplications();
      setMyApplications(data);
    } catch (err) {
      console.error("Failed to load catalogue applications", err);
    } finally {
      setApplicationsLoading(false);
    }
  };

  const loadMyPhotoProposals = async () => {
    try {
      const data = await api.catalogue.listPhotoProposals();
      setMyPhotoProposals(data);
    } catch (err) {
      console.error("Failed to load catalogue photo proposals", err);
    }
  };

  const handleSubmitApplication = async () => {
    setAppModalError("");
    const resolvedMakeName = appMakeMode === "CUSTOM"
      ? appMakeName.trim()
      : (makes.find((m) => m.id === appMakeId)?.name || "").trim();

    if (!resolvedMakeName) {
      setAppModalError("Vehicle Make is required.");
      return;
    }
    if (!appModelName.trim()) {
      setAppModalError("Vehicle Model Name is required.");
      return;
    }
    const yStart = parseInt(appYearStart, 10);
    if (isNaN(yStart) || yStart < 1900 || yStart > 2050) {
      setAppModalError("Please provide a valid start year (1900 - 2050).");
      return;
    }
    let yEnd: number | null = null;
    if (appYearEnd.trim()) {
      yEnd = parseInt(appYearEnd, 10);
      if (isNaN(yEnd) || yEnd < yStart) {
        setAppModalError("End year cannot be before start year.");
        return;
      }
    }

    setAppSubmitting(true);
    try {
      const payload: CreateVehicleCatalogueApplicationPayload = {
        make: appMakeMode === "SELECT" && appMakeId ? appMakeId : null,
        make_name: resolvedMakeName,
        model_name: appModelName.trim(),
        year_start: yStart,
        year_end: yEnd,
        variant_name: appVariantName.trim() || undefined,
        year: appYear.trim() ? parseInt(appYear, 10) : undefined,
        fuel_type: appFuel,
        transmission: appTrans,
        body_type: appBody.trim(),
        engine_code: appEngineCode.trim(),
        power_bhp: appPowerBhp.trim() ? parseInt(appPowerBhp, 10) : undefined,
        engine_capacity_cc: appEngineCapacityCc.trim() ? parseInt(appEngineCapacityCc, 10) : undefined,
        primary_image_url: appPrimaryImageUrl.trim(),
        images: appImages,
        notes: appNotes.trim(),
      };

      await api.catalogue.submitApplication(payload);
      setSuccessMessage("Vehicle catalogue application submitted successfully! It is pending admin review.");
      setAppModalOpen(false);
      resetApplicationForm();
      loadMyApplications();
    } catch (err: unknown) {
      setAppModalError(err instanceof Error ? err.message : "Failed to submit vehicle application.");
    } finally {
      setAppSubmitting(false);
    }
  };

  const handleProposePhoto = async () => {
    setProposalError("");
    if (!proposalModelId) {
      setProposalError("Model is required.");
      return;
    }
    if (!proposedUrl.trim()) {
      setProposalError("Please enter a proposed image URL.");
      return;
    }
    try {
      new URL(proposedUrl.trim());
    } catch {
      setProposalError("Please provide a valid image URL.");
      return;
    }

    setProposalLoading(true);
    try {
      await api.catalogue.submitPhotoProposal({
        model: proposalModelId,
        proposed_image_url: proposedUrl.trim(),
        notes: proposalNotes.trim(),
      });
      setSuccessMessage("Catalogue photo proposal submitted successfully! Pending admin review.");
      setPhotoProposalOpen(false);
      setProposedUrl("");
      setProposalNotes("");
      loadMyPhotoProposals();
    } catch (err: unknown) {
      setProposalError(err instanceof Error ? err.message : "Failed to submit photo proposal.");
    } finally {
      setProposalLoading(false);
    }
  };

  // Load reference datasets
  useEffect(() => {
    api.catalogue.getMakes().then(setMakes).catch(console.error);
    api.catalogue.getCategories().then(setCategories).catch(console.error);
    api.catalogue.getParts().then(setCatalogueParts).catch(console.error);
    api.catalogue.getVariants().then(setVariants).catch(console.error);
    api.marketplace.getGstOptions().then((res) => {
      if (res) {
        const list = res.options || res.hsn_options || [];
        setHsnOptions(list);
      }
    }).catch(console.error);
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

  // Load variants when model changes (or reload all catalogue variants when no model selected)
  useEffect(() => {
    let ignore = false;
    api.catalogue.getVariants(vehModel || undefined).then((res) => {
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
    } else if (activeSection === "parts") {
  if (statusFilter === "LOW_STOCK") {
        api.marketplace.listLowStockParts().then((data) => {
          if (!ignore) {
            setParts(data);
            setPartsLoading(false);
          }
        }).catch((err) => {
          if (!ignore) {
            console.error("Failed to load low stock parts", err);
            setPartsLoading(false);
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
    } else if (activeSection === "applications") {
  Promise.resolve().then(() => {
    if (!ignore) {
      loadMyApplications();
      loadMyPhotoProposals();
    }
  });
} else if (activeSection === "enquiries") {
      Promise.resolve().then(() => {
        if (!ignore) {
          setEnquiriesLoading(true);
        }
      });
      const st = enquiryStatusFilter !== "ALL" ? enquiryStatusFilter : undefined;
      api.marketplace.listSellerEnquiries({ status: st }).then((data) => {
        if (!ignore) {
          setEnquiries(data);
          const drafts: Record<string, string> = {};
          data.forEach((e) => {
            drafts[e.id] = e.seller_notes || "";
          });
          setSellerNotesDraft(drafts);
          setEnquiriesLoading(false);
        }
      }).catch((err) => {
        if (!ignore) {
          console.error("Failed to load seller enquiries", err);
          setEnquiriesLoading(false);
        }
      });
    }
    return () => {
      ignore = true;
    };
  }, [activeSection, statusFilter, enquiryStatusFilter]);

  const handleUpdateEnquiryStatus = async (enquiryId: string, newStatus: VehicleEnquiryStatus) => {
    setUpdatingEnquiryId(enquiryId);
    try {
      const updated = await api.marketplace.updateSellerEnquiry(enquiryId, {
        status: newStatus,
        seller_notes: sellerNotesDraft[enquiryId],
      });
      setEnquiries((prev) => prev.map((e) => (e.id === enquiryId ? updated : e)));
    } catch (err) {
      console.error("Failed to update enquiry status", err);
    } finally {
      setUpdatingEnquiryId(null);
    }
  };

  const handleSaveEnquiryNote = async (enquiryId: string) => {
    setSavingNoteId(enquiryId);
    try {
      const note = sellerNotesDraft[enquiryId] || "";
      const updated = await api.marketplace.updateSellerEnquiry(enquiryId, {
        seller_notes: note,
      });
      setEnquiries((prev) => prev.map((e) => (e.id === enquiryId ? updated : e)));
    } catch (err) {
      console.error("Failed to save enquiry note", err);
    } finally {
      setSavingNoteId(null);
    }
  };

  const handleSendSellerReply = async (enquiryId: string) => {
    const replyText = (sellerReplyDraft[enquiryId] || "").trim();
    if (!replyText) {
      setReplyError((prev) => ({ ...prev, [enquiryId]: "Please type a reply message before sending." }));
      return;
    }

    setReplyingEnquiryId(enquiryId);
    setReplyError((prev) => ({ ...prev, [enquiryId]: "" }));
    try {
      const updated = await api.marketplace.updateSellerEnquiry(enquiryId, {
        seller_reply: replyText,
      });
      setEnquiries((prev) => prev.map((e) => (e.id === enquiryId ? updated : e)));
      setSellerReplyDraft((prev) => ({ ...prev, [enquiryId]: "" }));
      setReplySuccessId(enquiryId);
      setTimeout(() => {
        setReplySuccessId((prev) => (prev === enquiryId ? null : prev));
      }, 4000);
    } catch (err: unknown) {
      console.error("Failed to send seller reply", err);
      const msg = err instanceof Error ? err.message : "Failed to send reply. Please try again.";
      setReplyError((prev) => ({
        ...prev,
        [enquiryId]: msg,
      }));
    } finally {
      setReplyingEnquiryId(null);
    }
  };

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
        primary_image_url: vehPrimaryImageUrl.trim(),
        images: vehImages,
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
    let parsedCompareAt: number | null = null;
    if (partCompareAtPrice.trim()) {
      parsedCompareAt = parseFloat(partCompareAtPrice);
      if (isNaN(parsedCompareAt) || parsedCompareAt <= 0) {
        setPartModalError("Compare-at price must be greater than £0.00.");
        return;
      }
      if (parsedCompareAt <= parsedPrice) {
        setPartModalError("Compare-at price must be strictly greater than asking price.");
        return;
      }
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
        catalogue_part: partCataloguePart || null,
        price: parsedPrice,
        compare_at_price: parsedCompareAt,
        hsn_code: partHsnCode || undefined,
        gst_rate: partGstRate ? parseFloat(partGstRate) : undefined,
        currency: "GBP",
        stock_quantity: parsedStock,
        condition: partCondition,
        description: partDescription.trim(),
        primary_image_url: partPrimaryImageUrl.trim(),
        images: partImages,
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
      const conflictInfo = parseConflictDetails(err);
      if (conflictInfo.conflicts && conflictInfo.conflicts.length > 0) {
        setConflictModal({
          title: "Submission Blocked: Fitment Conflict Detected",
          message: conflictInfo.message,
          conflicts: conflictInfo.conflicts,
        });
      }
      setPartModalError(conflictInfo.message);
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
      const conflictInfo = parseConflictDetails(err);
      if (conflictInfo.conflicts && conflictInfo.conflicts.length > 0) {
        setConflictModal({
          title: "Submission Blocked: Fitment Conflict Detected",
          message: conflictInfo.message,
          conflicts: conflictInfo.conflicts,
        });
      }
      setErrorMessage(conflictInfo.message);
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
      const conflictInfo = parseConflictDetails(err);
      if (conflictInfo.conflicts && conflictInfo.conflicts.length > 0) {
        setConflictModal({
          title: "Resubmission Blocked: Fitment Conflict Detected",
          message: conflictInfo.message,
          conflicts: conflictInfo.conflicts,
        });
      }
      setErrorMessage(conflictInfo.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Save Edit Vehicle (Phase 4)
  const handleSaveEditVehicle = async () => {
    if (!editingVehicle) return;
    setActionLoading(true);
    setVehModalError("");
    try {
      await api.marketplace.updateVehicle(editingVehicle.id, {
        price: parseFloat(editVehPrice),
        mileage: parseInt(editVehMileage, 10),
        description: editVehDescription,
        primary_image_url: editVehPrimaryImageUrl.trim(),
        images: editVehImages,
      });
      setSuccessMessage(
        editingVehicle.status === "APPROVED"
          ? "Vehicle updated! Material fields were modified, so it has been returned to Pending Approval for review."
          : "Vehicle details updated successfully."
      );
      setEditingVehicle(null);
      const data = await api.marketplace.listMyVehicles(statusFilter === "ALL" ? undefined : statusFilter);
      setVehicles(data);
    } catch (err: unknown) {
      setVehModalError(err instanceof Error ? err.message : "Failed to update vehicle.");
    } finally {
      setActionLoading(false);
    }
  };

  // Save Edit Part (Phase 4 / Phase 3: stock_quantity removed from update payload)
  const handleSaveEditPart = async () => {
    if (!editingPart) return;
    setActionLoading(true);
    setPartModalError("");

    const parsedPrice = parseFloat(editPartPrice);
    if (isNaN(parsedPrice) || parsedPrice <= 0) {
      setPartModalError("Retail price must be greater than £0.00.");
      setActionLoading(false);
      return;
    }

    let parsedCompareAt: number | null = null;
    if (editPartCompareAtPrice.trim()) {
      parsedCompareAt = parseFloat(editPartCompareAtPrice);
      if (isNaN(parsedCompareAt) || parsedCompareAt <= 0) {
        setPartModalError("Compare-at price must be greater than £0.00.");
        setActionLoading(false);
        return;
      }
      if (parsedCompareAt <= parsedPrice) {
        setPartModalError("Compare-at price must be strictly greater than retail price.");
        setActionLoading(false);
        return;
      }
    }

    try {
      const updatePayload: Partial<CreatePartListingPayload> = {
        description: editPartDescription,
        primary_image_url: editPartPrimaryImageUrl.trim(),
        images: editPartImages,
      };
      if (canManageListing(editingPart)) {
        updatePayload.price = parsedPrice;
        updatePayload.compare_at_price = parsedCompareAt;
        updatePayload.catalogue_part = editPartCataloguePart || null;
        updatePayload.compatible_variants = editPartVariant ? [editPartVariant] : [];
        updatePayload.compatibility_notes = editPartCompatibilityNotes.trim();
        updatePayload.hsn_code = editPartHsnCode || undefined;
        updatePayload.gst_rate = editPartGstRate ? parseFloat(editPartGstRate) : undefined;
      }

      await api.marketplace.updatePart(editingPart.id, updatePayload);

      let initialVarId = "";
      if (Array.isArray(editingPart.compatible_variants) && editingPart.compatible_variants.length > 0) {
        const first = editingPart.compatible_variants[0] as unknown;
        if (typeof first === "object" && first !== null && "id" in first) {
          initialVarId = String((first as { id: string }).id);
        } else if (typeof first === "string") {
          initialVarId = first;
        }
      } else if (editingPart.fitment_verification && editingPart.fitment_verification.length > 0) {
        initialVarId = editingPart.fitment_verification[0].variant_id || "";
      }

      const isMaterial =
        parsedPrice !== Number(editingPart.price) ||
        parsedCompareAt !== (editingPart.compare_at_price ? Number(editingPart.compare_at_price) : null) ||
        (editPartCataloguePart || null) !== (editingPart.catalogue_part || null) ||
        editPartDescription !== (editingPart.description || "") ||
        editPartVariant !== initialVarId ||
        editPartCompatibilityNotes.trim() !== (editingPart.compatibility_notes || "").trim() ||
        editPartHsnCode !== (editingPart.hsn_code || "") ||
        parseFloat(editPartGstRate) !== Number(editingPart.gst_rate || 0);
      setSuccessMessage(
        editingPart.status === "APPROVED" && isMaterial
          ? "Spare part updated! Material fields were modified, so it has been returned to Pending Approval for review."
          : "Spare part details updated successfully."
      );
      setEditingPart(null);
      const data = await api.marketplace.listMyParts(statusFilter === "ALL" ? undefined : statusFilter);
      setParts(data);
    } catch (err: unknown) {
      const conflictInfo = parseConflictDetails(err);
      if (conflictInfo.conflicts && conflictInfo.conflicts.length > 0) {
        setConflictModal({
          title: "Update Blocked: Fitment Conflict Detected",
          message: conflictInfo.message,
          conflicts: conflictInfo.conflicts,
        });
      }
      setPartModalError(conflictInfo.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Stock Adjustment Handlers (Phase 3 Part A)
  const handleOpenStockAdjust = (part: MarketplacePartListing) => {
    setAdjustingPart(part);
    setAdjustDelta("");
    setAdjustReason("ADJUSTMENT");
    setAdjustNote("");
    setAdjustModalError("");
  };

  const handleSubmitStockAdjust = async () => {
    if (!adjustingPart) return;
    setAdjustModalError("");
    const deltaNum = parseInt(adjustDelta, 10);
    if (isNaN(deltaNum) || deltaNum === 0) {
      setAdjustModalError("Adjustment delta cannot be zero. Enter a positive or negative integer.");
      return;
    }
    const resultingStock = adjustingPart.stock_quantity + deltaNum;
    if (resultingStock < 0) {
      setAdjustModalError(`Adjustment would result in negative stock (${resultingStock}). Current stock is ${adjustingPart.stock_quantity}.`);
      return;
    }

    setActionLoading(true);
    try {
      const res = await api.marketplace.adjustPartStock(adjustingPart.id, {
        delta: deltaNum,
        reason: adjustReason,
        note: adjustNote.trim(),
      });
      setSuccessMessage(
        `Stock for ${adjustingPart.name} adjusted successfully (${deltaNum > 0 ? `+${deltaNum}` : deltaNum}). New stock: ${res.listing.stock_quantity} units.`
      );
      setAdjustingPart(null);
      const data = await api.marketplace.listMyParts(statusFilter === "ALL" ? undefined : statusFilter);
      setParts(data);
    } catch (err: unknown) {
      setAdjustModalError(err instanceof Error ? err.message : "Failed to adjust stock.");
    } finally {
      setActionLoading(false);
    }
  };

  // Stock History Handler (Phase 3 Part A)
  const handleOpenStockHistory = async (part: MarketplacePartListing) => {
    setHistoryPart(part);
    setHistoryLoading(true);
    try {
      const movements = await api.marketplace.getPartStockHistory(part.id);
      setStockMovements(movements);
    } catch (err: unknown) {
      console.error("Failed to load stock history", err);
      setStockMovements([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Price History Handler (Phase 3 Part B)
  const handleOpenPriceHistory = async (part: MarketplacePartListing) => {
    setPriceHistoryPart(part);
    setPriceHistoryLoading(true);
    try {
      const history = await api.marketplace.getPartPriceHistory(part.id);
      setPriceChanges(history);
    } catch (err: unknown) {
      console.error("Failed to load price history", err);
      setPriceChanges([]);
    } finally {
      setPriceHistoryLoading(false);
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
          ) : activeSection === "parts" ? (
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
          ) : activeSection === "applications" ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setErrorMessage("");
                  setProposalError("");
                  setPhotoProposalOpen(true);
                }}
                className="px-3.5 py-2.5 bg-slate-800 hover:bg-slate-700 text-amber-400 text-xs font-bold rounded-xl transition-all border border-slate-700 flex items-center gap-1.5"
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Propose Official Photo</span>
              </button>
              <button
                onClick={() => {
                  setErrorMessage("");
                  setAppModalError("");
                  setAppModalOpen(true);
                }}
                className="px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                <span>Submit Vehicle to Catalogue</span>
              </button>
            </div>
          ) : (
            <button
              onClick={() => {
                setEnquiriesLoading(true);
                api.marketplace
                  .listSellerEnquiries({
                    status: enquiryStatusFilter !== "ALL" ? enquiryStatusFilter : undefined,
                  })
                  .then((data) => {
                    setEnquiries(data);
                    setEnquiriesLoading(false);
                  })
                  .catch(() => setEnquiriesLoading(false));
              }}
              className="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
              <span>Refresh Enquiries</span>
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
          <button
            onClick={() => {
              setActiveSection("applications");
              setStatusFilter("ALL");
            }}
            className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              activeSection === "applications"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            <FilePlus className="w-3.5 h-3.5" />
            <span>Catalogue Submissions</span>
          </button>
          <button
            onClick={() => {
              setActiveSection("enquiries");
              setEnquiryStatusFilter("ALL");
            }}
            className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              activeSection === "enquiries"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-amber-500" />
            <span>Vehicle Enquiries</span>
            {enquiries.filter((e) => e.status === "NEW").length > 0 && (
              <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-amber-500 text-slate-950">
                {enquiries.filter((e) => e.status === "NEW").length}
              </span>
            )}
          </button>
        </div>

        {/* Status Pills */}
        {activeSection === "enquiries" ? (
          <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto text-xs pb-1 sm:pb-0">
            {[
              { id: "ALL", label: "All Enquiries" },
              { id: "NEW", label: "New Enquiries" },
              { id: "RESPONDED", label: "Responded" },
              { id: "CLOSED", label: "Closed" },
            ].map((st) => (
              <button
                key={st.id}
                onClick={() => setEnquiryStatusFilter(st.id)}
                className={`px-3 py-1.5 rounded-xl font-bold whitespace-nowrap transition-colors ${
                  enquiryStatusFilter === st.id
                    ? "bg-slate-900 text-white"
                    : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
                }`}
              >
                {st.label}
              </button>
            ))}
          </div>
        ) : activeSection !== "applications" ? (
          <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto text-xs pb-1 sm:pb-0">
            {(activeSection === "parts"
              ? ["ALL", "LOW_STOCK", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "DRAFT"]
              : ["ALL", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "DRAFT"]
            ).map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1.5 rounded-xl font-bold whitespace-nowrap transition-colors ${
                  statusFilter === st
                    ? "bg-slate-900 text-white"
                    : st === "LOW_STOCK"
                    ? "bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200"
                    : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
                }`}
              >
                {st === "ALL"
                  ? "All Statuses"
                  : st === "LOW_STOCK"
                  ? "⚠ Low Stock Only"
                  : st === "PENDING_APPROVAL"
                  ? "Pending"
                  : st === "CHANGES_REQUESTED"
                  ? "Action Req."
                  : st.charAt(0) + st.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-500 font-medium flex items-center gap-2">
            <span>Catalogue proposals undergo compliance review before official inclusion.</span>
          </div>
        )}
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
                          <img src={resolveMediaUrl(v.primary_image_url)} alt={v.title} className="w-full h-full object-cover" />
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
                      <div className="mt-2">
                        {canManageListing(v) ? (
                          <button
                            onClick={() => {
                              setEditingVehicle(v);
                              setEditVehPrice(String(v.price));
                              setEditVehMileage(String(v.mileage));
                              setEditVehDescription(v.description || "");
                              setEditVehPrimaryImageUrl(v.primary_image_url || "");
                              setEditVehImages(Array.isArray(v.images) ? v.images : []);
                              setVehModalError("");
                            }}
                            className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition-colors inline-flex items-center gap-1"
                          >
                            <Pencil className="w-3 h-3" />
                            <span>Edit Listing</span>
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-400 font-medium px-2 py-0.5 bg-slate-50 border border-slate-200 rounded">
                            Read-only org role
                          </span>
                        )}
                      </div>
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
                        {canResubmitListing(v) ? (
                          <button
                            onClick={() => handleResubmitVehicle(v.id)}
                            disabled={actionLoading}
                            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5 disabled:opacity-50"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            <span>Resubmit Vehicle For Approval</span>
                          </button>
                        ) : (
                          <span className="text-xs text-slate-400 font-medium italic">
                            Resubmit disabled: Read-only organisation role (requires listing seller or organisation OWNER/ADMIN).
                          </span>
                        )}
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
                    <div className="flex items-start gap-4">
                      <div className="w-20 h-16 rounded-2xl bg-slate-900 overflow-hidden flex-shrink-0 flex items-center justify-center">
                        {p.primary_image_url ? (
                          <img src={resolveMediaUrl(p.primary_image_url)} alt={p.name} className="w-full h-full object-cover" />
                        ) : (
                          <Wrench className="w-6 h-6 text-slate-700" />
                        )}
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">
                            {p.brand}
                          </span>
                        {renderStatusBadge(p.status)}
                        {/* Availability Badge (Phase 3 Part A) */}
                        {p.availability === "OUT_OF_STOCK" || p.stock_quantity === 0 ? (
                          <span className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[10px] font-bold border border-rose-200 flex items-center gap-1">
                            <XCircle className="w-3 h-3" />
                            <span>Out of Stock</span>
                          </span>
                        ) : p.availability === "LOW_STOCK" || p.stock_quantity <= (p.low_stock_threshold ?? 3) ? (
                          <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            <span>Low Stock ({p.stock_quantity} left)</span>
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            <span>In Stock ({p.stock_quantity})</span>
                          </span>
                        )}
                      </div>
                      <h4 className="text-base font-black text-slate-950">{p.name}</h4>
                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-[10px]">
                          MPN: {p.mpn}
                        </span>
                        <span>Category: {p.category_name || "General"}</span>
                        {p.catalogue_part_name && (
                          <span className="text-amber-800 font-bold bg-amber-50 px-2 py-0.5 rounded text-[10px] border border-amber-200">
                            Catalogue: {p.catalogue_part_name}
                          </span>
                        )}
                        <span>Stock: <strong className="text-slate-900">{p.stock_quantity}</strong> units (Threshold: {p.low_stock_threshold ?? 3})</span>
                        <span>Condition: {p.condition}</span>
                        {p.organisation_name && (
                          <span className="flex items-center gap-1 text-slate-700 font-medium">
                            <Building2 className="w-3 h-3 text-slate-400" />
                            <span>{p.organisation_name}</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                    <div className="text-right sm:self-center flex flex-col items-end">
                      <span className="text-xs text-slate-400">Retail Price (excl. GST)</span>
                      <div className="flex items-baseline gap-1.5">
                        {p.compare_at_price && Number(p.compare_at_price) > Number(p.price) && (
                          <span className="text-xs text-slate-400 line-through">
                            ₹{Number(p.compare_at_price).toFixed(2)}
                          </span>
                        )}
                        <span className="text-xl font-black text-slate-950">
                          ₹{Number(p.price).toFixed(2)}
                        </span>
                      </div>
                      {p.gst_rate !== undefined && p.gst_rate !== null && (
                        <div className="text-right text-[11px] text-slate-500 mt-0.5 space-y-0.5">
                          <div>
                            GST ({Number(p.gst_rate).toFixed(0)}%): <span className="font-semibold text-slate-700">₹{p.gst_amount ? Number(p.gst_amount).toFixed(2) : (Number(p.price) * Number(p.gst_rate) / 100).toFixed(2)}</span>
                          </div>
                          <div className="text-[11px] font-bold text-emerald-700">
                            Total: ₹{p.total_price ? Number(p.total_price).toFixed(2) : (Number(p.price) * (1 + Number(p.gst_rate) / 100)).toFixed(2)}
                          </div>
                          {p.hsn_code && (
                            <span className="inline-block px-1.5 py-0.5 rounded text-[9px] font-mono bg-slate-100 text-slate-600 border border-slate-200">
                              HSN {p.hsn_code} {p.is_tax_verified ? "✓ Verified" : "⚠️ Needs Verification"}
                            </span>
                          )}
                        </div>
                      )}
                      <div className="mt-2 flex flex-wrap items-center justify-end gap-1.5">
                        {/* Adjust Stock Button (Phase 3 Part A) */}
                        {canManageListing(p) ? (
                          <button
                            onClick={() => handleOpenStockAdjust(p)}
                            className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-900 border border-amber-300 text-xs font-bold rounded-lg transition-colors inline-flex items-center gap-1"
                          >
                            <Sliders className="w-3 h-3" />
                            <span>Adjust Stock</span>
                          </button>
                        ) : (
                          <span
                            className="text-[10px] text-slate-400 font-medium px-2 py-0.5 bg-slate-50 border border-slate-200 rounded cursor-not-allowed"
                            title="Stock adjustments restricted for read-only organisation role"
                          >
                            Adjust: Read-only
                          </span>
                        )}

                        {/* Stock History Button (Phase 3 Part A) */}
                        <button
                          onClick={() => handleOpenStockHistory(p)}
                          className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition-colors inline-flex items-center gap-1"
                        >
                          <History className="w-3 h-3" />
                          <span>Stock History</span>
                        </button>

                        {/* Price History Button (Phase 3 Part B) */}
                        <button
                          onClick={() => handleOpenPriceHistory(p)}
                          className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition-colors inline-flex items-center gap-1"
                        >
                          <Clock className="w-3 h-3" />
                          <span>Price History</span>
                        </button>

                        {/* Edit Listing Button */}
                        {canManageListing(p) ? (
                          <button
                            onClick={() => {
                              setEditingPart(p);
                              setEditPartPrice(String(p.price));
                              setEditPartCompareAtPrice(p.compare_at_price ? String(p.compare_at_price) : "");
                              setEditPartCataloguePart(p.catalogue_part || "");
                              setEditPartDescription(p.description || "");
                              setEditPartPrimaryImageUrl(p.primary_image_url || "");
                              setEditPartImages(Array.isArray(p.images) ? p.images : []);
                              setEditPartHsnCode(p.hsn_code || "8708");
                              setEditPartGstRate(p.gst_rate !== undefined && p.gst_rate !== null ? String(p.gst_rate) : "28.00");

                              let currentVarId = "";
                              if (Array.isArray(p.compatible_variants) && p.compatible_variants.length > 0) {
                                const first = p.compatible_variants[0] as unknown;
                                if (typeof first === "object" && first !== null && "id" in first) {
                                  currentVarId = String((first as { id: string }).id);
                                } else if (typeof first === "string") {
                                  currentVarId = first;
                                }
                              } else if (p.fitment_verification && p.fitment_verification.length > 0) {
                                currentVarId = p.fitment_verification[0].variant_id || "";
                              }
                              setEditPartVariant(currentVarId);
                              setEditPartCompatibilityNotes(p.compatibility_notes || "");

                              setPartModalError("");
                            }}
                            className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition-colors inline-flex items-center gap-1"
                          >
                            <Pencil className="w-3 h-3" />
                            <span>Edit</span>
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-400 font-medium px-2 py-0.5 bg-slate-50 border border-slate-200 rounded">
                            Edit: Read-only
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Fitment Verification & Summary (Phase 3 Part C) */}
                  {((p.fitment_verification && p.fitment_verification.length > 0) || p.fitment_summary) && (
                    <div className="p-3 bg-slate-50/80 rounded-2xl border border-slate-200/80 space-y-2 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold text-slate-800 text-[11px] flex items-center gap-1.5">
                          <Wrench className="w-3.5 h-3.5 text-slate-500" />
                          <span>Vehicle Fitment Verification</span>
                        </span>
                        {p.fitment_summary && (
                          <div className="flex flex-wrap items-center gap-1.5">
                            {p.fitment_summary.conflict > 0 && (
                              <span className="px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 text-[10px] font-bold border border-rose-300 flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3 text-rose-600" />
                                <span>{p.fitment_summary.conflict} Conflict (Blocking)</span>
                              </span>
                            )}
                            {p.fitment_summary.verified > 0 && (
                              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                                {p.fitment_summary.verified} Verified
                              </span>
                            )}
                            {p.fitment_summary.conditional > 0 && (
                              <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 text-[10px] font-bold border border-amber-200">
                                {p.fitment_summary.conditional} Conditional
                              </span>
                            )}
                            {p.fitment_summary.seller_claimed > 0 && (
                              <span className="px-2 py-0.5 rounded-full bg-sky-50 text-sky-800 text-[10px] font-bold border border-sky-200">
                                {p.fitment_summary.seller_claimed} Seller-Claimed
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      {p.fitment_verification && p.fitment_verification.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {p.fitment_verification.map((v) => (
                            <span
                              key={v.variant_id}
                              className={`px-2 py-0.5 rounded-lg text-[10px] font-medium border flex items-center gap-1 ${
                                v.status === "VERIFIED"
                                  ? "bg-emerald-50 text-emerald-900 border-emerald-200"
                                  : v.status === "CONDITIONAL"
                                  ? "bg-amber-50 text-amber-900 border-amber-200"
                                  : v.status === "CONFLICT"
                                  ? "bg-rose-100 text-rose-900 border-rose-300 font-bold"
                                  : "bg-sky-50 text-sky-900 border-sky-200"
                              }`}
                            >
                              <span>
                                {v.status === "VERIFIED"
                                  ? "Verified:"
                                  : v.status === "CONDITIONAL"
                                  ? "Conditional:"
                                  : v.status === "CONFLICT"
                                  ? "CONFLICT:"
                                  : "Claimed:"}{" "}
                                {v.display_name}
                              </span>
                              {v.qualifications && (
                                <span className="text-[9px] opacity-80 italic">({v.qualifications})</span>
                              )}
                            </span>
                          ))}
                        </div>
                      ) : p.fitment_summary &&
                        (p.fitment_summary.verified ?? 0) === 0 &&
                        (p.fitment_summary.conditional ?? 0) === 0 &&
                        (p.fitment_summary.seller_claimed ?? 0) === 0 &&
                        (p.fitment_summary.conflict ?? 0) === 0 ? (
                        <p className="text-[11px] text-slate-500 italic pt-0.5">
                          No compatible variants declared for this listing.
                        </p>
                      ) : null}
                    </div>
                  )}

                  {/* Draft Notice & Publish Button */}
                  {p.status === "DRAFT" && (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-slate-50 border border-slate-200 rounded-2xl text-xs">
                      <div className="flex items-center gap-2 text-slate-700">
                        <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                        <span>This spare part is saved as a <strong>Draft</strong>. It is not published or sent for review until submitted.</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {p.fitment_summary && p.fitment_summary.conflict > 0 && (
                          <span className="text-[11px] text-rose-700 font-bold flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                            <span>Cannot submit: resolve conflict</span>
                          </span>
                        )}
                        <button
                          onClick={() => handlePublishDraftPart(p.id)}
                          disabled={actionLoading || Boolean(p.fitment_summary && p.fitment_summary.conflict > 0)}
                          className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50 shrink-0"
                          title={p.fitment_summary && p.fitment_summary.conflict > 0 ? "Submission blocked due to conflicting fitments" : undefined}
                        >
                          {actionLoading ? <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <RotateCcw className="w-3.5 h-3.5 text-amber-400" />}
                          <span>Submit For Approval</span>
                        </button>
                      </div>
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
                      <div className="flex items-center justify-between pt-1">
                        {p.fitment_summary && p.fitment_summary.conflict > 0 ? (
                          <span className="text-xs text-rose-700 font-bold flex items-center gap-1.5">
                            <AlertTriangle className="w-4 h-4 text-rose-600" />
                            <span>Resubmission blocked: Part has conflicting vehicle fitments. Remove conflicts first.</span>
                          </span>
                        ) : <div />}
                        {canResubmitListing(p) ? (
                          <button
                            onClick={() => handleResubmitPart(p.id)}
                            disabled={actionLoading || Boolean(p.fitment_summary && p.fitment_summary.conflict > 0)}
                            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5 disabled:opacity-50"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            <span>Resubmit Part For Approval</span>
                          </button>
                        ) : (
                          <span className="text-xs text-slate-400 font-medium italic">
                            Resubmit disabled: Read-only organisation role (requires listing seller or organisation OWNER/ADMIN).
                          </span>
                        )}
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
          SECTION 3: CATALOGUE APPLICATIONS & PHOTO PROPOSALS
      ========================================================================= */}
      {activeSection === "applications" && (
        <div className="space-y-8">
          {/* Applications Subsection */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-black text-slate-900 flex items-center gap-2">
                  <FilePlus className="w-4 h-4 text-amber-500" />
                  <span>Submitted Vehicle Applications</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Applications to add unlisted vehicle makes/models into the approved DriverXtra catalogue.
                </p>
              </div>
              <button
                onClick={() => setAppModalOpen(true)}
                className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5 text-amber-400" />
                <span>New Application</span>
              </button>
            </div>

            {applicationsLoading ? (
              <div className="py-12 text-center bg-white rounded-3xl border border-slate-200">
                <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <p className="text-xs text-slate-500 font-medium">Loading applications...</p>
              </div>
            ) : myApplications.length === 0 ? (
              <div className="bg-white rounded-3xl p-8 text-center border border-slate-200 space-y-3">
                <Car className="w-10 h-10 text-slate-300 mx-auto" />
                <h4 className="text-sm font-bold text-slate-900">No Vehicle Applications Submitted</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  If you have a vehicle whose model is not in the DriverXtra catalogue, apply to have it added. Once approved by admin, you can list it for sale.
                </p>
                <button
                  onClick={() => setAppModalOpen(true)}
                  className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-xl transition-colors inline-flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Submit New Vehicle Application</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {myApplications.map((app) => (
                  <div key={app.id} className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[11px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                            {app.make_name || "Custom Make"}
                          </span>
                          {app.status === "APPROVED" ? (
                            <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>Approved</span>
                            </span>
                          ) : app.status === "REJECTED" ? (
                            <span className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[10px] font-bold border border-rose-200 flex items-center gap-1">
                              <XCircle className="w-3 h-3" />
                              <span>Rejected</span>
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200 flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              <span>Pending Review</span>
                            </span>
                          )}
                        </div>
                        <h4 className="text-base font-black text-slate-950">
                          {app.model_name}
                          {app.variant_name && <span className="text-slate-500 font-normal"> · {app.variant_name}</span>}
                        </h4>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Production: {app.year_start}
                          {app.year_end ? ` – ${app.year_end}` : " – Present"}
                          {app.fuel_type && ` · ${app.fuel_type}`}
                          {app.transmission && ` · ${app.transmission}`}
                          {app.body_type && ` · ${app.body_type}`}
                        </p>
                      </div>
                    </div>

                    {/* Image Preview */}
                    {(app.primary_image_url || (app.images && app.images.length > 0)) && (
                      <div className="flex items-center gap-2 pt-1 overflow-x-auto">
                        {app.primary_image_url && (
                          <div className="w-16 h-12 rounded-xl bg-slate-900 overflow-hidden flex-shrink-0 relative border border-amber-400">
                            <img
                              src={app.primary_image_url}
                              alt="Primary"
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = "none";
                              }}
                            />
                            <span className="absolute bottom-0 inset-x-0 bg-black/60 text-[8px] text-amber-300 text-center font-bold">
                              Primary
                            </span>
                          </div>
                        )}
                        {app.images?.filter((img) => img !== app.primary_image_url).map((img, i) => (
                          <div key={i} className="w-16 h-12 rounded-xl bg-slate-100 overflow-hidden flex-shrink-0 border border-slate-200">
                            <img
                              src={img}
                              alt={`Thumbnail ${i + 1}`}
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = "none";
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Rejection / Reviewer feedback */}
                    {app.status === "REJECTED" && app.rejection_reason && (
                      <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-900 space-y-1">
                        <span className="font-bold flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                          <span>Rejection Reason</span>
                        </span>
                        <p className="text-rose-800">{app.rejection_reason}</p>
                      </div>
                    )}
                    {app.status === "APPROVED" && (
                      <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 flex items-center gap-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span>Catalogue entry created. You can now select this vehicle when adding listings.</span>
                      </div>
                    )}

                    <div className="pt-2 border-t border-slate-100 text-[10px] text-slate-400 flex items-center justify-between">
                      <span>Submitted: {new Date(app.created_at).toLocaleDateString()}</span>
                      {app.reviewed_at && <span>Reviewed: {new Date(app.reviewed_at).toLocaleDateString()}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Catalogue Photo Proposals Subsection */}
          <div className="space-y-4 pt-4 border-t border-slate-200">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-black text-slate-900 flex items-center gap-2">
                  <Camera className="w-4 h-4 text-amber-500" />
                  <span>Proposed Official Catalogue Photos</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Proposals to update or provide high-resolution canonical photos for approved catalogue models.
                </p>
              </div>
              <button
                onClick={() => setPhotoProposalOpen(true)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-amber-400 text-xs font-bold rounded-xl transition-colors border border-slate-700 flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Propose Photo</span>
              </button>
            </div>

            {myPhotoProposals.length === 0 ? (
              <div className="bg-white rounded-3xl p-8 text-center border border-slate-200 space-y-3">
                <Camera className="w-10 h-10 text-slate-300 mx-auto" />
                <h4 className="text-sm font-bold text-slate-900">No Photo Proposals Submitted</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Notice an approved vehicle model in the catalogue with missing or low-resolution imagery? Propose an updated official photo for admin moderation.
                </p>
                <button
                  onClick={() => setPhotoProposalOpen(true)}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors inline-flex items-center gap-1.5"
                >
                  <Camera className="w-3.5 h-3.5 text-amber-400" />
                  <span>Propose Official Photo</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {myPhotoProposals.map((prop) => (
                  <div key={prop.id} className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">
                          {prop.make_name || "Catalogue Model"}
                        </span>
                        <h4 className="text-sm font-black text-slate-950">{prop.model_name}</h4>
                      </div>
                      {prop.status === "APPROVED" ? (
                        <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Approved</span>
                        </span>
                      ) : prop.status === "REJECTED" ? (
                        <span className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[10px] font-bold border border-rose-200 flex items-center gap-1">
                          <XCircle className="w-3 h-3" />
                          <span>Rejected</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <span>Pending Review</span>
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-3 pt-1">
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Current Official</span>
                        <div className="h-20 bg-slate-100 rounded-xl overflow-hidden border border-slate-200 flex items-center justify-center">
                          {prop.current_image_url ? (
                            <img src={prop.current_image_url} alt="Current" className="w-full h-full object-cover" />
                          ) : (
                            <span className="text-[10px] text-slate-400 italic">None</span>
                          )}
                        </div>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider block">Proposed</span>
                        <div className="h-20 bg-slate-100 rounded-xl overflow-hidden border border-amber-300 flex items-center justify-center">
                          <img
                            src={prop.proposed_image_url}
                            alt="Proposed"
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = "none";
                            }}
                          />
                        </div>
                      </div>
                    </div>

                    {prop.notes && (
                      <p className="text-xs text-slate-600 bg-slate-50 p-2.5 rounded-xl border border-slate-100 italic">
                        &quot;{prop.notes}&quot;
                      </p>
                    )}

                    {prop.status === "REJECTED" && (prop.rejection_reason || prop.admin_notes) && (
                      <div className="p-2.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800">
                        <strong>Rejection reason:</strong> {prop.rejection_reason || prop.admin_notes}
                      </div>
                    )}
                    {prop.status === "APPROVED" && (
                      <div className="p-2 bg-emerald-50 border border-emerald-200 rounded-xl text-[11px] text-emerald-800">
                        ✓ Approved: Catalogue vehicle image updated successfully.
                      </div>
                    )}

                    <div className="pt-2 border-t border-slate-100 text-[10px] text-slate-400 flex items-center justify-between">
                      <span>Submitted: {new Date(prop.created_at).toLocaleDateString()}</span>
                      {prop.reviewed_at && <span>Reviewed: {new Date(prop.reviewed_at).toLocaleDateString()}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          SECTION 4: VEHICLE ENQUIRIES MANAGEMENT
      ========================================================================= */}
      {activeSection === "enquiries" && (
        <div className="space-y-4">
          {/* Header metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="p-3.5 bg-white rounded-2xl border border-slate-200">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Total Enquiries</span>
              <p className="text-xl font-black text-slate-900 mt-0.5">{enquiries.length}</p>
            </div>
            <div className="p-3.5 bg-white rounded-2xl border border-amber-200 bg-amber-50/30">
              <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider block">New / Pending</span>
              <p className="text-xl font-black text-amber-600 mt-0.5">
                {enquiries.filter((e) => e.status === "NEW").length}
              </p>
            </div>
            <div className="p-3.5 bg-white rounded-2xl border border-emerald-200 bg-emerald-50/30">
              <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider block">Responded</span>
              <p className="text-xl font-black text-emerald-600 mt-0.5">
                {enquiries.filter((e) => e.status === "RESPONDED").length}
              </p>
            </div>
            <div className="p-3.5 bg-white rounded-2xl border border-slate-200">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Closed</span>
              <p className="text-xl font-black text-slate-600 mt-0.5">
                {enquiries.filter((e) => e.status === "CLOSED").length}
              </p>
            </div>
          </div>

          {enquiriesLoading ? (
            <div className="p-12 text-center bg-white rounded-3xl border border-slate-200 flex flex-col items-center justify-center">
              <Loader2 className="w-8 h-8 text-amber-500 animate-spin mb-3" />
              <p className="text-sm font-bold text-slate-700">Loading incoming vehicle enquiries...</p>
              <p className="text-xs text-slate-400 mt-1">Connecting to DriverXtra marketplace lead manager</p>
            </div>
          ) : enquiries.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-3xl border border-slate-200 max-w-lg mx-auto space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mx-auto">
                <MessageSquare className="w-6 h-6" />
              </div>
              <h4 className="text-base font-black text-slate-900">No Vehicle Enquiries Found</h4>
              <p className="text-xs text-slate-500 leading-relaxed">
                {enquiryStatusFilter !== "ALL"
                  ? `There are currently no enquiries with status "${enquiryStatusFilter}".`
                  : "When prospective buyers browse your approved vehicles on the marketplace and send direct questions, they will appear here with full buyer contact details."}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {enquiries.map((enq) => {
                const isNew = enq.status === "NEW";
                const isResponded = enq.status === "RESPONDED";
                const isClosed = enq.status === "CLOSED";
                const isUpdating = updatingEnquiryId === enq.id;
                const isSavingNote = savingNoteId === enq.id;
                const isReplying = replyingEnquiryId === enq.id;

                return (
                  <div
                    key={enq.id}
                    className={`bg-white rounded-3xl border transition-all p-5 space-y-4 ${
                      isNew
                        ? "border-amber-300 shadow-md ring-1 ring-amber-300/40"
                        : "border-slate-200 shadow-sm hover:border-slate-300"
                    }`}
                  >
                    {/* Top Row: Vehicle Summary + Status Badge */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                      <div className="flex items-center gap-3">
                        {enq.listing_details?.primary_image_url ? (
                          <img
                            src={resolveMediaUrl(enq.listing_details.primary_image_url)}
                            alt={enq.listing_details.title || "Vehicle"}
                            className="w-12 h-12 rounded-xl object-cover border border-slate-200 flex-shrink-0"
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 flex-shrink-0">
                            <Car className="w-6 h-6" />
                          </div>
                        )}
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-black text-slate-900">
                              {enq.listing_details?.title || "Vehicle Listing"}
                            </h4>
                            <span className="text-xs font-mono font-bold text-amber-600">
                              £{Number(enq.listing_details?.price || 0).toLocaleString()}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-500 flex items-center gap-2 mt-0.5">
                            <span>Year: {enq.listing_details?.year || "N/A"}</span>
                            <span>·</span>
                            <span>Location: {enq.listing_details?.location_city || "UK"}</span>
                            <span>·</span>
                            <span className="font-mono text-[10px]">Ref: #{enq.id.slice(0, 8)}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 self-start sm:self-auto">
                        {isNew && (
                          <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300 flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                            New Enquiry
                          </span>
                        )}
                        {isResponded && (
                          <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1.5">
                            <Check className="w-3 h-3 text-emerald-600" />
                            Responded
                          </span>
                        )}
                        {isClosed && (
                          <span className="px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-300">
                            Closed
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Middle Row: Buyer details & Buyer message */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Buyer Identity Card */}
                      <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 space-y-2 text-xs">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          Buyer Contact Details
                        </span>
                        <div>
                          <span className="text-slate-500 block text-[10px]">Name</span>
                          <span className="font-bold text-slate-900">{enq.buyer_name || "DriverXtra Buyer"}</span>
                        </div>
                        <div>
                          <span className="text-slate-500 block text-[10px]">Email</span>
                          <a
                            href={`mailto:${enq.buyer_email}`}
                            className="font-medium text-amber-700 hover:underline flex items-center gap-1 truncate"
                          >
                            <Mail className="w-3 h-3 text-slate-400 flex-shrink-0" />
                            <span className="truncate">{enq.buyer_email}</span>
                          </a>
                        </div>
                        {enq.buyer_phone ? (
                          <div>
                            <span className="text-slate-500 block text-[10px]">Callback Phone</span>
                            <div className="flex items-center gap-2 mt-0.5">
                              <a
                                href={`tel:${enq.buyer_phone}`}
                                className="font-mono text-slate-900 font-bold hover:underline flex items-center gap-1"
                              >
                                <Phone className="w-3 h-3 text-emerald-600" />
                                <span>{enq.buyer_phone}</span>
                              </a>
                              <a
                                href={`https://wa.me/${enq.buyer_phone.replace(/\D/g, "")}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-1 rounded-lg bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
                                title="Chat on WhatsApp"
                              >
                                <MessageCircle className="w-3.5 h-3.5" />
                              </a>
                            </div>
                          </div>
                        ) : (
                          <div>
                            <span className="text-slate-500 block text-[10px]">Callback Phone</span>
                            <span className="text-slate-400 italic">None provided (Email only)</span>
                          </div>
                        )}
                        <div className="pt-1 text-[10px] text-slate-400">
                          Received: {new Date(enq.created_at).toLocaleString()}
                        </div>
                      </div>

                      {/* Buyer Message Bubble & Seller Reply Section */}
                      <div className="md:col-span-2 flex flex-col space-y-3">
                        {/* Buyer Message */}
                        <div className="p-4 bg-amber-50/60 rounded-2xl border border-amber-200/80 space-y-1.5">
                          <div className="flex items-center justify-between text-[11px] font-bold text-amber-900">
                            <span className="flex items-center gap-1">
                              <MessageSquare className="w-3.5 h-3.5 text-amber-600" />
                              <span>Buyer&apos;s Message</span>
                            </span>
                            <span className="font-normal text-[10px] text-amber-700">
                              {new Date(enq.created_at).toLocaleDateString()}
                            </span>
                          </div>
                          <p className="text-xs text-slate-800 whitespace-pre-line leading-relaxed">
                            {enq.message}
                          </p>
                        </div>

                        {/* Existing In-Platform Reply Display */}
                        {enq.seller_reply && (
                          <div className="p-4 bg-emerald-50/70 rounded-2xl border border-emerald-200 space-y-1.5">
                            <div className="flex items-center justify-between text-[11px] font-bold text-emerald-900">
                              <span className="flex items-center gap-1.5">
                                <Send className="w-3.5 h-3.5 text-emerald-600" />
                                <span>Your Reply to Buyer (In-Platform)</span>
                              </span>
                              {enq.replied_at && (
                                <span className="font-normal text-[10px] text-emerald-700">
                                  Sent {new Date(enq.replied_at).toLocaleString()}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-800 whitespace-pre-line leading-relaxed">
                              {enq.seller_reply}
                            </p>
                          </div>
                        )}

                        {/* Reply to Buyer Form */}
                        <div className="p-4 bg-slate-50/90 rounded-2xl border border-slate-200 space-y-2.5">
                          <div className="flex items-center justify-between">
                            <label className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                              <MessageSquare className="w-3.5 h-3.5 text-amber-600" />
                              <span>{enq.seller_reply ? "Update Reply to Buyer" : "Reply to Buyer"}</span>
                            </label>
                            <span className="text-[10px] text-amber-700 font-medium">
                              Buyer will see this reply in their dashboard
                            </span>
                          </div>
                          <textarea
                            rows={2}
                            value={sellerReplyDraft[enq.id] ?? ""}
                            onChange={(e) => {
                              setSellerReplyDraft((prev) => ({
                                ...prev,
                                [enq.id]: e.target.value,
                              }));
                              if (replyError[enq.id]) {
                                setReplyError((prev) => ({ ...prev, [enq.id]: "" }));
                              }
                            }}
                            placeholder="Type your message to the buyer (e.g. Yes, the vehicle is available for inspection this Saturday at 2 PM...)"
                            className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
                          />
                          {replyError[enq.id] && (
                            <div className="text-[11px] text-rose-600 font-medium flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3 text-rose-500" />
                              <span>{replyError[enq.id]}</span>
                            </div>
                          )}
                          {replySuccessId === enq.id && (
                            <div className="text-[11px] text-emerald-700 font-medium flex items-center gap-1 bg-emerald-50 px-2.5 py-1.5 rounded-xl border border-emerald-200">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                              <span>Reply sent successfully! Buyer can now view it under My Enquiries.</span>
                            </div>
                          )}
                          <div className="flex justify-end">
                            <button
                              type="button"
                              onClick={() => handleSendSellerReply(enq.id)}
                              disabled={isReplying || !(sellerReplyDraft[enq.id]?.trim())}
                              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold rounded-xl text-xs flex items-center gap-1.5 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {isReplying ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  <span>Sending...</span>
                                </>
                              ) : (
                                <>
                                  <Send className="w-3.5 h-3.5" />
                                  <span>Send Reply</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Internal Private Notes (Clearly separate from buyer reply) */}
                        <div className="p-3 bg-slate-100/70 rounded-2xl border border-slate-200/80 space-y-2">
                          <div className="flex items-center gap-1.5 text-slate-600">
                            <Lock className="w-3 h-3 text-slate-500" />
                            <span className="text-[10px] font-bold uppercase tracking-wider">
                              Internal Private Notes (Not visible to buyer)
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={sellerNotesDraft[enq.id] ?? (enq.seller_notes || "")}
                              onChange={(e) =>
                                setSellerNotesDraft((prev) => ({
                                  ...prev,
                                  [enq.id]: e.target.value,
                                }))
                              }
                              placeholder="Add private note (e.g. called customer, arranged inspection)..."
                              className="flex-1 px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400"
                            />
                            <button
                              type="button"
                              onClick={() => handleSaveEnquiryNote(enq.id)}
                              disabled={isSavingNote}
                              className="px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-xl text-xs font-bold transition-colors disabled:opacity-50"
                            >
                              {isSavingNote ? "Saving..." : "Save Note"}
                            </button>
                          </div>
                        </div>

                        {/* Quick Lifecycle Action Buttons */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-100">
                          <div className="text-[11px] text-slate-500">
                            {enq.responded_at && (
                              <span>Responded on {new Date(enq.responded_at).toLocaleDateString()}</span>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            {enq.buyer_phone && (
                              <a
                                href={`tel:${enq.buyer_phone}`}
                                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-bold flex items-center gap-1"
                              >
                                <Phone className="w-3 h-3 text-emerald-600" />
                                <span>Call</span>
                              </a>
                            )}
                            <a
                              href={`mailto:${enq.buyer_email}?subject=${encodeURIComponent(
                                `RE: Enquiry for ${enq.listing_details?.title || "Vehicle"}`
                              )}`}
                              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-bold flex items-center gap-1"
                            >
                              <Mail className="w-3 h-3 text-amber-600" />
                              <span>Email</span>
                            </a>

                            {isNew && (
                              <button
                                type="button"
                                onClick={() => handleUpdateEnquiryStatus(enq.id, "RESPONDED")}
                                disabled={isUpdating}
                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1 shadow-sm disabled:opacity-50"
                              >
                                <Check className="w-3 h-3" />
                                <span>Mark Responded</span>
                              </button>
                            )}

                            {!isClosed ? (
                              <button
                                type="button"
                                onClick={() => handleUpdateEnquiryStatus(enq.id, "CLOSED")}
                                disabled={isUpdating}
                                className="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-xl text-xs font-bold transition-all disabled:opacity-50"
                              >
                                Close
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={() => handleUpdateEnquiryStatus(enq.id, "NEW")}
                                disabled={isUpdating}
                                className="px-3 py-1.5 bg-amber-100 hover:bg-amber-200 text-amber-900 rounded-xl text-xs font-bold transition-all disabled:opacity-50"
                              >
                                Re-open
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
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
                  <p className="text-[10px] text-slate-500 mt-1 flex items-center justify-between">
                    <span>Model not listed?</span>
                    <button
                      type="button"
                      onClick={() => {
                        setAddVehicleOpen(false);
                        setAppModalOpen(true);
                      }}
                      className="text-amber-600 hover:text-amber-700 font-bold underline"
                    >
                      Apply to add vehicle
                    </button>
                  </p>
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
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
              </div>

              <div>
                <ListingPhotoManager
                  title="Vehicle Listing Photos"
                  description="Add up to 10 photos of this vehicle from your computer. Choose a primary image for search cards."
                  primaryImageUrl={vehPrimaryImageUrl}
                  images={vehImages}
                  onChange={(primary, imgs) => {
                    setVehPrimaryImageUrl(primary);
                    setVehImages(imgs);
                  }}
                  listingType="vehicle"
                  maxImages={10}
                />
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

              {/* Optional Catalogue Part Picker */}
              <div>
                <label className="block text-slate-700 font-bold mb-1">Catalogue Master Part (Optional)</label>
                <select
                  value={partCataloguePart}
                  onChange={(e) => setPartCataloguePart(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                >
                  <option value="">Unlinked / Standalone Part</option>
                  {catalogueParts.map((cp) => (
                    <option key={cp.id} value={cp.id}>
                      {cp.name} ({cp.brand} · MPN: {cp.mpn || cp.part_number})
                    </option>
                  ))}
                </select>
                <span className="text-[10px] text-slate-500 mt-1 block">
                  Linking to an active catalogue part enables multi-seller comparison offers.
                </span>
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

              {/* Price, Compare-At, Stock, Condition */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Price (£) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={partPrice}
                    onChange={(e) => setPartPrice(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Compare-At (£)</label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="e.g. 149.99"
                    value={partCompareAtPrice}
                    onChange={(e) => setPartCompareAtPrice(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                  {partCompareAtPrice && parseFloat(partCompareAtPrice) <= parseFloat(partPrice) && (
                    <span className="text-[9px] text-amber-600 font-bold block mt-0.5">
                      Must be &gt; £{partPrice}
                    </span>
                  )}
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

              {/* Statutory GST & HSN Classification */}
              <div className="p-4 bg-slate-900 text-white rounded-2xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-amber-400">Statutory GST & HSN Classification</span>
                    <span className="text-[10px] text-slate-400">(Indian CBIC Rules)</span>
                  </div>
                  {(() => {
                    const selectedHsnObj = hsnOptions.find((h) => h.hsn_code === partHsnCode);
                    return selectedHsnObj?.is_verified ? (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/30 text-[9px] font-bold">
                        ✓ Verified Schedule
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[9px] font-bold">
                        ⚠️ Requires Admin Verification
                      </span>
                    );
                  })()}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 text-[11px] font-bold mb-1">
                      HSN / Product Classification *
                    </label>
                    <select
                      value={partHsnCode}
                      onChange={(e) => {
                        const newHsn = e.target.value;
                        setPartHsnCode(newHsn);
                        const match = hsnOptions.find((h) => h.hsn_code === newHsn);
                        if (match) {
                          setPartGstRate(match.standard_rate);
                        }
                      }}
                      className="w-full px-3 py-2 bg-slate-800 border border-slate-700 text-white rounded-xl focus:outline-none focus:border-amber-500 text-xs"
                    >
                      {hsnOptions.length > 0 ? (
                        hsnOptions.map((opt) => (
                          <option key={opt.hsn_code} value={opt.hsn_code}>
                            HSN {opt.hsn_code} — {opt.description} ({opt.standard_rate}%)
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="8708">HSN 8708 — Parts and accessories of motor vehicles (28%)</option>
                          <option value="8421">HSN 8421 — Oil, air, fuel filters (18%)</option>
                          <option value="8413">HSN 8413 — Fuel pumps, water pumps (18%)</option>
                          <option value="8507">HSN 8507 — Electric accumulators & batteries (28%)</option>
                          <option value="8409">HSN 8409 — Internal combustion engine parts (28%)</option>
                          <option value="4011">HSN 4011 — Pneumatic tyres for motor vehicles (28%)</option>
                        </>
                      )}
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-300 text-[11px] font-bold mb-1">
                      Applicable GST Rate (%) *
                    </label>
                    <select
                      value={partGstRate}
                      onChange={(e) => setPartGstRate(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-800 border border-slate-700 text-white rounded-xl focus:outline-none focus:border-amber-500 text-xs font-mono"
                    >
                      {(() => {
                        const selectedHsnObj = hsnOptions.find((h) => h.hsn_code === partHsnCode);
                        const permitted: string[] = selectedHsnObj?.permitted_rates || selectedHsnObj?.allowed_rates || ["28.00", "18.00", "12.00", "5.00"];
                        return permitted.map((r: string) => (
                          <option key={r} value={r}>
                            {r}% {r === selectedHsnObj?.standard_rate ? "(Statutory Standard)" : "(Concessional / Specific Variant)"}
                          </option>
                        ));
                      })()}
                    </select>
                  </div>
                </div>

                {/* Live Tax Breakdown Calculation */}
                {(() => {
                  const pNum = parseFloat(partPrice) || 0;
                  const rNum = parseFloat(partGstRate) || 0;
                  const taxAmount = (pNum * rNum / 100);
                  const grandTotal = pNum + taxAmount;
                  return (
                    <div className="pt-2 border-t border-slate-800 grid grid-cols-3 gap-2 text-center text-xs">
                      <div className="bg-slate-800/80 p-2 rounded-xl">
                        <span className="text-[10px] text-slate-400 block">Part Price (excl.)</span>
                        <span className="font-bold text-slate-200">₹{pNum.toFixed(2)}</span>
                      </div>
                      <div className="bg-slate-800/80 p-2 rounded-xl">
                        <span className="text-[10px] text-slate-400 block">GST ({rNum.toFixed(0)}%)</span>
                        <span className="font-bold text-amber-400">+ ₹{taxAmount.toFixed(2)}</span>
                      </div>
                      <div className="bg-amber-500/10 border border-amber-500/30 p-2 rounded-xl">
                        <span className="text-[10px] text-amber-300 block font-semibold">Total Price</span>
                        <span className="font-black text-amber-400">₹{grandTotal.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })()}
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
                        {v.display_name || `${v.name} (${v.engine_code || v.fuel_type})`}
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
                <ListingPhotoManager
                  title="Spare Part Photos"
                  description="Add up to 10 photos of the spare part, packaging, or part number stamp from your computer."
                  primaryImageUrl={partPrimaryImageUrl}
                  images={partImages}
                  onChange={(primary, imgs) => {
                    setPartPrimaryImageUrl(primary);
                    setPartImages(imgs);
                  }}
                  listingType="part"
                  maxImages={10}
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

      {/* =========================================================================
          MODAL: EDIT VEHICLE LISTING (Phase 4)
      ========================================================================= */}
      {editingVehicle && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[calc(100dvh-2rem)] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Car className="w-4 h-4 text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">
                  Edit Vehicle: {editingVehicle.title}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setEditingVehicle(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            {/* Warning banner when approved */}
            {editingVehicle.status === "APPROVED" && (
              <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-xs text-amber-900 font-semibold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Editing will send this listing back for review</span>
              </div>
            )}

            {vehModalError && (
              <div className="p-3 bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold rounded-xl">
                {vehModalError}
              </div>
            )}

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1">Asking Price (£)</label>
                <input
                  type="number"
                  value={editVehPrice}
                  onChange={(e) => setEditVehPrice(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Mileage</label>
                <input
                  type="number"
                  value={editVehMileage}
                  onChange={(e) => setEditVehMileage(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Description</label>
                <textarea
                  rows={3}
                  value={editVehDescription}
                  onChange={(e) => setEditVehDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              <div>
                <ListingPhotoManager
                  title="Vehicle Listing Photos"
                  description="Update, upload, or reorder photos for this vehicle listing."
                  primaryImageUrl={editVehPrimaryImageUrl}
                  images={editVehImages}
                  onChange={(primary, imgs) => {
                    setEditVehPrimaryImageUrl(primary);
                    setEditVehImages(imgs);
                  }}
                  listingType="vehicle"
                  listingId={editingVehicle?.id}
                  maxImages={10}
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingVehicle(null)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEditVehicle}
                disabled={actionLoading}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Save Changes</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: EDIT PART LISTING (Phase 4)
      ========================================================================= */}
      {editingPart && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[calc(100dvh-2rem)] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Wrench className="w-4 h-4 text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">
                  Edit Spare Part: {editingPart.name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setEditingPart(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            {/* Warning banner when approved */}
            {editingPart.status === "APPROVED" && (
              <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-xs text-amber-900 font-semibold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Changing price, compare-at price, catalogue link or compatible variant sends this listing back for review.</span>
              </div>
            )}

            {!canManageListing(editingPart) && (
              <div className="p-2.5 bg-slate-100 border border-slate-200 rounded-xl text-[11px] text-slate-600 font-medium">
                Price and catalogue controls are restricted for read-only organisation roles.
              </div>
            )}

            {partModalError && (
              <div className="p-3 bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold rounded-xl">
                {partModalError}
              </div>
            )}

            <div className="space-y-3 text-xs">
              {/* Catalogue Part Picker */}
              <div>
                <label className="block text-slate-700 font-bold mb-1">Catalogue Master Part</label>
                <select
                  value={editPartCataloguePart}
                  onChange={(e) => setEditPartCataloguePart(e.target.value)}
                  disabled={!canManageListing(editingPart)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none disabled:opacity-50 disabled:bg-slate-100"
                >
                  <option value="">Unlinked / Standalone Part</option>
                  {catalogueParts.map((cp) => (
                    <option key={cp.id} value={cp.id}>
                      {cp.name} ({cp.brand} · MPN: {cp.mpn || cp.part_number})
                    </option>
                  ))}
                </select>
              </div>

              {/* Compatible Variant & Notes */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">
                    Compatible Variant (Optional)
                  </label>
                  <select
                    value={editPartVariant}
                    onChange={(e) => setEditPartVariant(e.target.value)}
                    disabled={!canManageListing(editingPart)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none disabled:opacity-50 disabled:bg-slate-100"
                  >
                    <option value="">Universal / Unlinked</option>
                    {variants.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.display_name || `${v.name} (${v.engine_code || v.fuel_type})`}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Compatibility Notes</label>
                  <input
                    type="text"
                    placeholder="e.g. Fits 330i with M-Sport Brakes only"
                    value={editPartCompatibilityNotes}
                    onChange={(e) => setEditPartCompatibilityNotes(e.target.value)}
                    disabled={!canManageListing(editingPart)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none disabled:opacity-50 disabled:bg-slate-100"
                  />
                </div>
              </div>

              {/* Price and Compare-At Price */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Retail Price (£) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editPartPrice}
                    onChange={(e) => setEditPartPrice(e.target.value)}
                    disabled={!canManageListing(editingPart)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none disabled:opacity-50 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Compare-At Price (£)</label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="e.g. 149.99"
                    value={editPartCompareAtPrice}
                    onChange={(e) => setEditPartCompareAtPrice(e.target.value)}
                    disabled={!canManageListing(editingPart)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none disabled:opacity-50 disabled:bg-slate-100"
                  />
                  {editPartCompareAtPrice && parseFloat(editPartCompareAtPrice) <= parseFloat(editPartPrice) && (
                    <span className="text-[9px] text-amber-600 font-bold block mt-0.5">
                      Must be strictly greater than retail price (£{editPartPrice}).
                    </span>
                  )}
                </div>
              </div>

              {/* Statutory GST & HSN Classification (Edit Mode) */}
              <div className="p-4 bg-slate-900 text-white rounded-2xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-amber-400">Statutory GST & HSN Classification</span>
                    <span className="text-[10px] text-slate-400">(Indian CBIC Rules)</span>
                  </div>
                  {(() => {
                    const selectedHsnObj = hsnOptions.find((h) => h.hsn_code === editPartHsnCode);
                    return selectedHsnObj?.is_verified ? (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/30 text-[9px] font-bold">
                        ✓ Verified Schedule
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[9px] font-bold">
                        ⚠️ Requires Admin Verification
                      </span>
                    );
                  })()}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 text-[11px] font-bold mb-1">
                      HSN / Product Classification *
                    </label>
                    <select
                      value={editPartHsnCode}
                      onChange={(e) => {
                        const newHsn = e.target.value;
                        setEditPartHsnCode(newHsn);
                        const match = hsnOptions.find((h) => h.hsn_code === newHsn);
                        if (match) {
                          setEditPartGstRate(match.standard_rate);
                        }
                      }}
                      disabled={!canManageListing(editingPart)}
                      className="w-full px-3 py-2 bg-slate-800 border border-slate-700 text-white rounded-xl focus:outline-none focus:border-amber-500 text-xs disabled:opacity-50"
                    >
                      {hsnOptions.length > 0 ? (
                        hsnOptions.map((opt) => (
                          <option key={opt.hsn_code} value={opt.hsn_code}>
                            HSN {opt.hsn_code} — {opt.description} ({opt.standard_rate}%)
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="8708">HSN 8708 — Parts and accessories of motor vehicles (28%)</option>
                          <option value="8421">HSN 8421 — Oil, air, fuel filters (18%)</option>
                          <option value="8413">HSN 8413 — Fuel pumps, water pumps (18%)</option>
                          <option value="8507">HSN 8507 — Electric accumulators & batteries (28%)</option>
                          <option value="8409">HSN 8409 — Internal combustion engine parts (28%)</option>
                          <option value="4011">HSN 4011 — Pneumatic tyres for motor vehicles (28%)</option>
                        </>
                      )}
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-300 text-[11px] font-bold mb-1">
                      Applicable GST Rate (%) *
                    </label>
                    <select
                      value={editPartGstRate}
                      onChange={(e) => setEditPartGstRate(e.target.value)}
                      disabled={!canManageListing(editingPart)}
                      className="w-full px-3 py-2 bg-slate-800 border border-slate-700 text-white rounded-xl focus:outline-none focus:border-amber-500 text-xs font-mono disabled:opacity-50"
                    >
                      {(() => {
                        const selectedHsnObj = hsnOptions.find((h) => h.hsn_code === editPartHsnCode);
                        const permitted: string[] = selectedHsnObj?.permitted_rates || selectedHsnObj?.allowed_rates || ["28.00", "18.00", "12.00", "5.00"];
                        return permitted.map((r: string) => (
                          <option key={r} value={r}>
                            {r}% {r === selectedHsnObj?.standard_rate ? "(Statutory Standard)" : "(Concessional / Specific Variant)"}
                          </option>
                        ));
                      })()}
                    </select>
                  </div>
                </div>

                {/* Live Tax Breakdown Calculation */}
                {(() => {
                  const pNum = parseFloat(editPartPrice) || 0;
                  const rNum = parseFloat(editPartGstRate) || 0;
                  const taxAmount = (pNum * rNum / 100);
                  const grandTotal = pNum + taxAmount;
                  return (
                    <div className="pt-2 border-t border-slate-800 grid grid-cols-3 gap-2 text-center text-xs">
                      <div className="bg-slate-800/80 p-2 rounded-xl">
                        <span className="text-[10px] text-slate-400 block">Part Price (excl.)</span>
                        <span className="font-bold text-slate-200">₹{pNum.toFixed(2)}</span>
                      </div>
                      <div className="bg-slate-800/80 p-2 rounded-xl">
                        <span className="text-[10px] text-slate-400 block">GST ({rNum.toFixed(0)}%)</span>
                        <span className="font-bold text-amber-400">+ ₹{taxAmount.toFixed(2)}</span>
                      </div>
                      <div className="bg-amber-500/10 border border-amber-500/30 p-2 rounded-xl">
                        <span className="text-[10px] text-amber-300 block font-semibold">Total Price</span>
                        <span className="font-black text-amber-400">₹{grandTotal.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })()}
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Stock Quantity</label>
                <div className="w-full px-3 py-2 bg-slate-100 border border-slate-200 rounded-xl text-slate-700 font-bold flex items-center justify-between">
                  <span>{editingPart.stock_quantity} units</span>
                  <span className="text-[10px] font-bold text-slate-500 bg-slate-200 px-2 py-0.5 rounded">Read-only on edit</span>
                </div>
                <span className="text-[10px] text-slate-500 mt-1 block">
                  Direct stock edits via update are disabled. Use the dedicated <strong>Adjust Stock</strong> button on the inventory card to record an audit-logged adjustment.
                </span>
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Technical Description</label>
                <textarea
                  rows={3}
                  value={editPartDescription}
                  onChange={(e) => setEditPartDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              <div>
                <ListingPhotoManager
                  title="Spare Part Photos"
                  description="Update, upload, or reorder photos for this spare part listing."
                  primaryImageUrl={editPartPrimaryImageUrl}
                  images={editPartImages}
                  onChange={(primary, imgs) => {
                    setEditPartPrimaryImageUrl(primary);
                    setEditPartImages(imgs);
                  }}
                  listingType="part"
                  listingId={editingPart?.id}
                  maxImages={10}
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingPart(null)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEditPart}
                disabled={actionLoading}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Save Changes</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: STOCK ADJUSTMENT DIALOG (Phase 3 Part A)
      ========================================================================= */}
      {adjustingPart && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">
                  Adjust Inventory Stock
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setAdjustingPart(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <div className="bg-slate-50 p-3 rounded-2xl border border-slate-200 text-xs space-y-1">
              <div className="font-bold text-slate-900">{adjustingPart.name}</div>
              <div className="text-slate-500 flex justify-between">
                <span>Current Stock: <strong className="text-slate-900 font-mono">{adjustingPart.stock_quantity} units</strong></span>
                <span>Low Stock Threshold: <strong className="text-slate-900 font-mono">{adjustingPart.low_stock_threshold ?? 3} units</strong></span>
              </div>
            </div>

            {adjustModalError && (
              <div className="p-3 bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold rounded-xl">
                {adjustModalError}
              </div>
            )}

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1">Stock Delta (+ or -) *</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    placeholder="e.g. +5 or -2"
                    value={adjustDelta}
                    onChange={(e) => setAdjustDelta(e.target.value)}
                    className="flex-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500 font-mono text-sm"
                  />
                  <div className="flex gap-1">
                    {["+1", "+5", "+10", "-1", "-5"].map((btn) => (
                      <button
                        key={btn}
                        type="button"
                        onClick={() => setAdjustDelta(btn)}
                        className="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-bold rounded-lg"
                      >
                        {btn}
                      </button>
                    ))}
                  </div>
                </div>
                <span className="text-[10px] text-slate-400 mt-1 block">
                  Positive delta adds stock; negative delta deducts stock. Cannot be 0.
                </span>
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Adjustment Reason *</label>
                <select
                  value={adjustReason}
                  onChange={(e) => setAdjustReason(e.target.value as "ADJUSTMENT" | "CORRECTION")}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                >
                  <option value="ADJUSTMENT">ADJUSTMENT - Manual Stock Delivery / Shrinkage</option>
                  <option value="CORRECTION">CORRECTION - Inventory Audit / Reconciliation Correction</option>
                </select>
                <span className="text-[10px] text-slate-400 mt-0.5 block">
                  Note: INITIAL, SALE, and RETURN movements are reserved for system workflows.
                </span>
              </div>

              <div>
                <label className="block text-slate-700 font-bold mb-1">Internal Note (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Received shipment PO-4912 / recount discrepancy"
                  value={adjustNote}
                  onChange={(e) => setAdjustNote(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>

              {/* Projected Result Preview */}
              {adjustDelta && !isNaN(parseInt(adjustDelta, 10)) && (
                <div className="p-3 bg-slate-100 rounded-xl border border-slate-200 flex items-center justify-between">
                  <span className="text-slate-600 font-medium">Resulting Stock:</span>
                  <span
                    className={`font-black text-sm font-mono ${
                      adjustingPart.stock_quantity + parseInt(adjustDelta, 10) < 0
                        ? "text-red-600"
                        : adjustingPart.stock_quantity + parseInt(adjustDelta, 10) <= (adjustingPart.low_stock_threshold ?? 3)
                        ? "text-amber-600"
                        : "text-emerald-700"
                    }`}
                  >
                    {adjustingPart.stock_quantity + parseInt(adjustDelta, 10)} units
                    {adjustingPart.stock_quantity + parseInt(adjustDelta, 10) < 0 && " (Invalid: Negative stock prohibited)"}
                  </span>
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setAdjustingPart(null)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitStockAdjust}
                disabled={
                  actionLoading ||
                  !adjustDelta ||
                  isNaN(parseInt(adjustDelta, 10)) ||
                  parseInt(adjustDelta, 10) === 0 ||
                  adjustingPart.stock_quantity + parseInt(adjustDelta, 10) < 0
                }
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Apply Stock Adjustment</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: STOCK LEDGER HISTORY (Phase 3 Part A)
      ========================================================================= */}
      {historyPart && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[85vh] flex flex-col space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-slate-700" />
                <div>
                  <h3 className="text-sm font-black text-slate-900">
                    Stock Movement Audit Ledger
                  </h3>
                  <p className="text-[11px] text-slate-500 font-mono">
                    {historyPart.name} · Current Stock: {historyPart.stock_quantity} units
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setHistoryPart(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {historyLoading ? (
                <div className="py-12 text-center">
                  <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                  <p className="text-xs text-slate-500">Loading audit ledger...</p>
                </div>
              ) : stockMovements.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-xs">
                  No stock movements recorded for this listing yet.
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-12 text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1">
                    <span className="col-span-3">Timestamp</span>
                    <span className="col-span-2">Reason</span>
                    <span className="col-span-2 text-right">Delta</span>
                    <span className="col-span-2 text-right">Balance</span>
                    <span className="col-span-3 text-right">Actor / Note</span>
                  </div>

                  {stockMovements.map((m) => (
                    <div
                      key={m.id}
                      className="grid grid-cols-12 items-center text-xs p-3 bg-slate-50 hover:bg-slate-100 rounded-xl border border-slate-100 transition-colors"
                    >
                      <span className="col-span-3 text-[11px] text-slate-500">
                        {new Date(m.created_at).toLocaleString()}
                      </span>
                      <span className="col-span-2">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            m.reason === "INITIAL"
                              ? "bg-blue-50 text-blue-700 border border-blue-200"
                              : m.reason === "CORRECTION"
                              ? "bg-purple-50 text-purple-700 border border-purple-200"
                              : m.reason === "SALE"
                              ? "bg-orange-50 text-orange-700 border border-orange-200"
                              : m.reason === "RETURN"
                              ? "bg-teal-50 text-teal-700 border border-teal-200"
                              : "bg-slate-200 text-slate-800"
                          }`}
                        >
                          {m.reason}
                        </span>
                      </span>
                      <span
                        className={`col-span-2 text-right font-mono font-bold ${
                          m.delta > 0 ? "text-emerald-700" : "text-rose-700"
                        }`}
                      >
                        {m.delta > 0 ? `+${m.delta}` : m.delta}
                      </span>
                      <span className="col-span-2 text-right font-mono font-bold text-slate-900">
                        {m.resulting_quantity}
                      </span>
                      <div className="col-span-3 text-right truncate">
                        <span className="text-[11px] font-medium text-slate-700 block truncate">
                          {m.actor_name || "System"}
                        </span>
                        {m.note && (
                          <span className="text-[10px] text-slate-400 italic block truncate" title={m.note}>
                            {m.note}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Immutable Ledger · Rows locked with row-level mutex</span>
              <button
                type="button"
                onClick={() => setHistoryPart(null)}
                className="px-4 py-2 bg-slate-900 text-white rounded-xl font-bold hover:bg-slate-800"
              >
                Close Ledger
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: PRICE CHANGE AUDIT LEDGER (Phase 3 Part B)
      ========================================================================= */}
      {priceHistoryPart && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[85vh] flex flex-col space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-slate-700" />
                <div>
                  <h3 className="text-sm font-black text-slate-900">
                    Price Change Audit Ledger
                  </h3>
                  <p className="text-[11px] text-slate-500 font-mono">
                    {priceHistoryPart.name} · Current Price: £{Number(priceHistoryPart.price).toFixed(2)}
                    {priceHistoryPart.compare_at_price && (
                      <span className="text-slate-400"> (Compare-At: £{Number(priceHistoryPart.compare_at_price).toFixed(2)})</span>
                    )}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPriceHistoryPart(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {priceHistoryLoading ? (
                <div className="py-12 text-center">
                  <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                  <p className="text-xs text-slate-500">Loading price history...</p>
                </div>
              ) : priceChanges.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-xs">
                  No price changes recorded for this listing yet. (History begins upon the first price modification).
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-12 text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1">
                    <span className="col-span-3">Timestamp</span>
                    <span className="col-span-3">Price Adjustment</span>
                    <span className="col-span-3">Compare-At</span>
                    <span className="col-span-3 text-right">Actor / Note</span>
                  </div>

                  {priceChanges.map((pc) => (
                    <div
                      key={pc.id}
                      className="grid grid-cols-12 items-center text-xs p-3 bg-slate-50 hover:bg-slate-100 rounded-xl border border-slate-100 transition-colors"
                    >
                      <span className="col-span-3 text-[11px] text-slate-500">
                        {new Date(pc.created_at).toLocaleString()}
                      </span>
                      <div className="col-span-3 flex items-center gap-1 font-mono">
                        <span className="text-slate-500 line-through text-[11px]">
                          £{Number(pc.old_price).toFixed(2)}
                        </span>
                        <span className="text-slate-400">→</span>
                        <span className="font-bold text-slate-900">
                          £{Number(pc.new_price).toFixed(2)}
                        </span>
                      </div>
                      <div className="col-span-3 font-mono text-[11px]">
                        {pc.old_compare_at_price || pc.new_compare_at_price ? (
                          <div className="flex items-center gap-1">
                            <span className="text-slate-400">
                              {pc.old_compare_at_price ? `£${Number(pc.old_compare_at_price).toFixed(2)}` : "—"}
                            </span>
                            <span className="text-slate-400">→</span>
                            <span className="text-slate-700 font-semibold">
                              {pc.new_compare_at_price ? `£${Number(pc.new_compare_at_price).toFixed(2)}` : "—"}
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </div>
                      <div className="col-span-3 text-right truncate">
                        <span className="text-[11px] font-medium text-slate-700 block truncate">
                          {pc.actor_name || "System"}
                        </span>
                        {pc.note && (
                          <span className="text-[10px] text-slate-400 italic block truncate" title={pc.note}>
                            {pc.note}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Append-Only Ledger · Row-level mutex protection</span>
              <button
                type="button"
                onClick={() => setPriceHistoryPart(null)}
                className="px-4 py-2 bg-slate-900 text-white rounded-xl font-bold hover:bg-slate-800"
              >
                Close Ledger
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: FITMENT CONFLICT BLOCKING DIALOG (Phase 3 Part C)
      ========================================================================= */}
      {conflictModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4 border border-rose-200">
            <div className="flex items-center justify-between pb-3 border-b border-rose-100">
              <div className="flex items-center gap-2 text-rose-900">
                <ShieldAlert className="w-6 h-6 text-rose-600 shrink-0" />
                <h3 className="text-base font-black text-rose-950">{conflictModal.title}</h3>
              </div>
              <button
                onClick={() => setConflictModal(null)}
                className="p-1 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <p className="text-slate-700 leading-relaxed font-medium">
                {conflictModal.message}
              </p>

              {conflictModal.conflicts && conflictModal.conflicts.length > 0 && (
                <div className="space-y-2 bg-rose-50/80 p-3.5 rounded-2xl border border-rose-200">
                  <span className="font-bold text-rose-900 block text-[11px] uppercase tracking-wider">
                    Conflicting Vehicle Fitments ({conflictModal.conflicts.length})
                  </span>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    {conflictModal.conflicts.map((c, idx) => (
                      <div key={idx} className="bg-white p-2.5 rounded-xl border border-rose-100 flex items-start gap-2">
                        <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-bold text-slate-900 block">
                            {c.display_name || c.variant_id}
                          </span>
                          <span className="text-[11px] text-rose-800 italic block">
                            Catalogue Note: {c.qualifications || "Confirmed does not fit by manufacturer catalogue"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className="text-[11px] text-slate-500">
                To submit or approve this listing, you must remove or correct the declared compatible variants that conflict with canonical catalogue records.
              </p>
            </div>

            <div className="pt-3 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setConflictModal(null)}
                className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-colors"
              >
                Acknowledge & Fix
              </button>
            </div>
          </div>
        </div>
      )}
      {/* =========================================================================
          MODAL: SUBMIT VEHICLE CATALOGUE APPLICATION
      ========================================================================= */}
      {appModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  Catalogue Application
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">Submit Vehicle for Catalogue Inclusion</h3>
              </div>
              <button
                onClick={() => setAppModalOpen(false)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {appModalError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-2xl text-xs font-bold text-red-900 flex items-center justify-between">
                <span>{appModalError}</span>
                <button
                  type="button"
                  onClick={() => setAppModalError("")}
                  className="text-red-700 hover:text-red-950 p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <div className="p-3 bg-amber-50/70 rounded-2xl border border-amber-200 text-xs text-amber-900 flex items-start gap-2">
              <HelpCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold block">Catalogue Approval Process</span>
                <span className="text-slate-600">
                  Approved applications create canonical vehicle models available to all sellers on DriverXtra.
                  This does not automatically create your sales listing. Once approved, you can create a listing with this model.
                </span>
              </div>
            </div>

            <div className="space-y-4 text-xs">
              {/* Make Mode */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-slate-700 font-bold">Vehicle Manufacturer / Make *</label>
                  <div className="flex items-center gap-2 text-[11px]">
                    <button
                      type="button"
                      onClick={() => setAppMakeMode("SELECT")}
                      className={`px-2 py-0.5 rounded-md font-bold ${
                        appMakeMode === "SELECT" ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900"
                      }`}
                    >
                      Existing Make
                    </button>
                    <button
                      type="button"
                      onClick={() => setAppMakeMode("CUSTOM")}
                      className={`px-2 py-0.5 rounded-md font-bold ${
                        appMakeMode === "CUSTOM" ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900"
                      }`}
                    >
                      New Make
                    </button>
                  </div>
                </div>

                {appMakeMode === "SELECT" ? (
                  <select
                    value={appMakeId}
                    onChange={(e) => setAppMakeId(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Select Existing Make</option>
                    {makes.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder="Enter new manufacturer name (e.g. Lucid, Polestar, BYD)"
                    value={appMakeName}
                    onChange={(e) => setAppMakeName(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                )}
              </div>

              {/* Model Name & Production Years */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-1">
                  <label className="block text-slate-700 font-bold mb-1">Model Name *</label>
                  <input
                    type="text"
                    placeholder="e.g. Air, Seal, Taycan"
                    value={appModelName}
                    onChange={(e) => setAppModelName(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Start Year *</label>
                  <input
                    type="number"
                    value={appYearStart}
                    onChange={(e) => setAppYearStart(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">End Year (Optional)</label>
                  <input
                    type="number"
                    placeholder="Leave blank if current"
                    value={appYearEnd}
                    onChange={(e) => setAppYearEnd(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
              </div>

              {/* Variant and Technical Specs */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Variant / Trim (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. Pure, Performance AWD"
                    value={appVariantName}
                    onChange={(e) => setAppVariantName(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Fuel Type</label>
                  <select
                    value={appFuel}
                    onChange={(e) => setAppFuel(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  >
                    <option value="PETROL">Petrol</option>
                    <option value="DIESEL">Diesel</option>
                    <option value="HYBRID">Hybrid</option>
                    <option value="EV">Electric (EV)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Transmission</label>
                  <select
                    value={appTrans}
                    onChange={(e) => setAppTrans(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  >
                    <option value="AUTOMATIC">Automatic</option>
                    <option value="MANUAL">Manual</option>
                    <option value="DUAL_CLUTCH">Dual Clutch</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Body Type</label>
                  <input
                    type="text"
                    placeholder="e.g. Saloon, SUV, Coupe"
                    value={appBody}
                    onChange={(e) => setAppBody(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Engine Code (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. B48B20"
                    value={appEngineCode}
                    onChange={(e) => setAppEngineCode(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-bold mb-1">Power (BHP)</label>
                  <input
                    type="number"
                    placeholder="e.g. 258"
                    value={appPowerBhp}
                    onChange={(e) => setAppPowerBhp(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                  />
                </div>
              </div>

              {/* Photos */}
              <div>
                <ListingPhotoManager
                  title="Vehicle Model Photos"
                  description="Upload official or clean press-quality images for this catalogue model. (Max 10 images)."
                  primaryImageUrl={appPrimaryImageUrl}
                  images={appImages}
                  onChange={(primary, imgs) => {
                    setAppPrimaryImageUrl(primary);
                    setAppImages(imgs);
                  }}
                  listingType="catalogue"
                  maxImages={10}
                />
              </div>

              {/* Notes */}
              <div>
                <label className="block text-slate-700 font-bold mb-1">Notes for Reviewer (Optional)</label>
                <textarea
                  rows={2}
                  value={appNotes}
                  onChange={(e) => setAppNotes(e.target.value)}
                  placeholder="Official OEM specs link, brochures, VIN example..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setAppModalOpen(false)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitApplication}
                disabled={appSubmitting}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {appSubmitting && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Submit Application For Review</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: PROPOSE CATALOGUE PHOTO
      ========================================================================= */}
      {photoProposalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Camera className="w-4 h-4 text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">
                  Propose Official Catalogue Photo
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setPhotoProposalOpen(false)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl text-xs text-amber-900">
              Propose an updated or missing image for an approved catalogue vehicle model. Proposals require admin approval before the canonical catalogue image is changed.
            </div>

            {proposalError && (
              <div className="p-3 bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold rounded-xl">
                {proposalError}
              </div>
            )}

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1">Vehicle Make *</label>
                <select
                  value={proposalMakeName}
                  onChange={(e) => {
                    const makeId = e.target.value;
                    const makeObj = makes.find((m) => m.id === makeId);
                    setProposalMakeName(makeId);
                    setProposalModelId("");
                    setProposalCurrentUrl("");
                    if (makeId) {
                      api.catalogue.getModels(makeId).then(setModels).catch(console.error);
                    }
                  }}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
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
                <label className="block text-slate-700 font-bold mb-1">Approved Model *</label>
                <select
                  value={proposalModelId}
                  onChange={(e) => {
                    const mid = e.target.value;
                    setProposalModelId(mid);
                    const selected = models.find((m) => m.id === mid);
                    setProposalModelName(selected?.name || "");
                    setProposalCurrentUrl(selected?.image_url || "");
                  }}
                  disabled={!proposalMakeName}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none disabled:opacity-50"
                >
                  <option value="">Select Model</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.year_start} – {m.year_end || "Present"})
                    </option>
                  ))}
                </select>
              </div>

              {/* Current photo preview */}
              {proposalModelId && (
                <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200 space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">
                    Current Official Photo
                  </span>
                  {proposalCurrentUrl ? (
                    <div className="h-24 rounded-lg bg-slate-900 overflow-hidden flex items-center justify-center">
                      <img src={resolveMediaUrl(proposalCurrentUrl)} alt="Current" className="w-full h-full object-cover" />
                    </div>
                  ) : (
                    <p className="text-slate-400 italic text-[11px]">No official photo currently set for this model.</p>
                  )}
                </div>
              )}

              <div>
                <input
                  type="file"
                  ref={proposalFileInputRef}
                  onChange={handleProposalFileUpload}
                  accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                  className="hidden"
                />
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-slate-700 font-bold">Proposed Image *</label>
                  <button
                    type="button"
                    disabled={proposalUploading}
                    onClick={() => proposalFileInputRef.current?.click()}
                    className="text-amber-600 hover:text-amber-700 font-bold text-[11px] flex items-center gap-1 transition-colors"
                  >
                    {proposalUploading ? (
                      <Loader2 className="w-3 h-3 animate-spin text-amber-500" />
                    ) : (
                      <Upload className="w-3 h-3 text-amber-500" />
                    )}
                    <span>{proposalUploading ? "Uploading..." : "Upload from Computer"}</span>
                  </button>
                </div>
                <input
                  type="url"
                  placeholder="Paste URL or click 'Upload from Computer' above"
                  value={proposedUrl}
                  onChange={(e) => setProposedUrl(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Preview of proposed image */}
              {proposedUrl && (
                <div className="space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">
                    Proposed Image Preview
                  </span>
                  <div className="h-28 rounded-xl bg-slate-900 overflow-hidden flex items-center justify-center border border-amber-400">
                    <img
                      src={resolveMediaUrl(proposedUrl)}
                      alt="Proposed preview"
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = "none";
                      }}
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-slate-700 font-bold mb-1">Notes for Reviewer (Optional)</label>
                <textarea
                  rows={2}
                  value={proposalNotes}
                  onChange={(e) => setProposalNotes(e.target.value)}
                  placeholder="e.g. Higher-resolution OEM press photo with transparent background..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setPhotoProposalOpen(false)}
                className="px-4 py-2 text-slate-600 hover:text-slate-900 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleProposePhoto}
                disabled={proposalLoading || !proposalModelId || !proposedUrl.trim()}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-1.5"
              >
                {proposalLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                <span>Submit Proposal</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
