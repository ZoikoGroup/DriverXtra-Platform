/**
 * DriverXtra API Client
 *
 * Lightweight, zero-dependency fetch wrapper for connecting to the Django REST Framework backend.
 * Base URL defaults to http://127.0.0.1:8000/api/v1
 *
 * Security considerations:
 * - Tokens are stored in sessionStorage (tab lifetime) rather than persistent localStorage,
 *   reducing exposure to persistent XSS attacks across sessions while preserving current-tab navigation.
 * - Sensitive values (passwords, tokens) are never logged to console.
 * - Concurrency lock prevents infinite refresh loops on 401 Unauthorized responses.
 */

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";

const STORAGE_KEYS = {
  ACCESS_TOKEN: "dx_access_token",
  REFRESH_TOKEN: "dx_refresh_token",
} as const;

export interface ApiErrorPayload {
  status: "error";
  code: number;
  message: string;
  details?: Record<string, string[] | string> | string[] | string;
}

export class ApiError extends Error {
  code: number;
  details?: Record<string, string[] | string> | string[] | string;

  constructor(message: string, code: number, details?: Record<string, string[] | string> | string[] | string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
  }
}

// In-memory token fallback if sessionStorage is unavailable (e.g. SSR)
let memoryAccessToken: string | null = null;
let memoryRefreshToken: string | null = null;

export const tokenStorage = {
  getAccessToken(): string | null {
    if (typeof window === "undefined") return memoryAccessToken;
    try {
      return sessionStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN) || memoryAccessToken;
    } catch {
      return memoryAccessToken;
    }
  },
  getRefreshToken(): string | null {
    if (typeof window === "undefined") return memoryRefreshToken;
    try {
      return sessionStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN) || memoryRefreshToken;
    } catch {
      return memoryRefreshToken;
    }
  },
  setTokens(access: string, refresh?: string): void {
    memoryAccessToken = access;
    if (refresh) memoryRefreshToken = refresh;
    if (typeof window !== "undefined") {
      try {
        sessionStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access);
        if (refresh) {
          sessionStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh);
        }
      } catch {
        // Ignore storage quotas / disabled storage
      }
    }
  },
  clearTokens(): void {
    memoryAccessToken = null;
    memoryRefreshToken = null;
    if (typeof window !== "undefined") {
      try {
        sessionStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        sessionStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
      } catch {
        // Ignore
      }
    }
  },
};

function getBaseUrl(): string {
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
  }
  return DEFAULT_BASE_URL;
}

// Concurrency lock for refresh requests
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) {
    tokenStorage.clearTokens();
    return null;
  }

  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const baseUrl = getBaseUrl();
      const res = await fetch(`${baseUrl}/auth/token/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: refreshToken }),
      });

      if (!res.ok) {
        if (res.status === 400 || res.status === 401) {
          tokenStorage.clearTokens();
        }
        return null;
      }

      const data = await res.json();
      const newAccess = data.access;
      const newRefresh = data.refresh || refreshToken;

      if (newAccess) {
        tokenStorage.setTokens(newAccess, newRefresh);
        return newAccess;
      }

      tokenStorage.clearTokens();
      return null;
    } catch (err: unknown) {
      console.warn("[Auth] Token refresh network failure:", {
        message: err instanceof Error ? err.message : "Network error",
      });
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

interface RequestOptions extends RequestInit {
  requiresAuth?: boolean;
  retryOn401?: boolean;
}

export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { requiresAuth = true, retryOn401 = true, headers: customHeaders, ...restOptions } = options;
  const baseUrl = getBaseUrl();
  const url = `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(customHeaders as Record<string, string>),
  };

  if (requiresAuth) {
    const token = tokenStorage.getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(url, { ...restOptions, headers });
  } catch {
    throw new ApiError(
      "Unable to connect to DriverXtra backend. Please ensure Django is running on http://127.0.0.1:8000.",
      0
    );
  }

  // Handle 401 Unauthorized with token refresh (once per request)
  if (response.status === 401 && requiresAuth && retryOn401) {
    const newAccessToken = await refreshAccessToken();
    if (newAccessToken) {
      const retryHeaders = {
        ...headers,
        Authorization: `Bearer ${newAccessToken}`,
      };
      try {
        response = await fetch(url, { ...restOptions, headers: retryHeaders });
      } catch {
        throw new ApiError("Network error during retried request.", 0);
      }
    } else {
      // Refresh failed or no refresh token - clear auth
      tokenStorage.clearTokens();
    }
  }

  // Parse response
  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    let message = "An unexpected error occurred.";
    let details: Record<string, string[] | string> | string[] | string | undefined = undefined;

    if (data && typeof data === "object") {
      const dataObj = data as Record<string, unknown>;
      if (typeof dataObj.error === "string") {
        message = dataObj.error;
      } else if (typeof dataObj.message === "string" && dataObj.message !== "Validation or execution error.") {
        message = dataObj.message;
      } else if (typeof dataObj.detail === "string") {
        message = dataObj.detail;
      }
      details = (dataObj.details || data) as Record<string, string[] | string> | string[] | string;

      // Extract field errors if present in details or the root payload
      const candidate = (dataObj.details && typeof dataObj.details === "object" ? dataObj.details : dataObj) as Record<string, unknown>;
      const fieldKeys = Object.keys(candidate).filter(
        (k) => !["status", "code", "message", "details", "detail", "error"].includes(k)
      );
      if (fieldKeys.length > 0) {
        const fieldErrors = fieldKeys.map((k) => {
          const val = candidate[k];
          if (Array.isArray(val) && val[0]) return `${k}: ${val[0]}`;
          if (typeof val === "string") return `${k}: ${val}`;
          return `${k}: ${JSON.stringify(val)}`;
        });
        message = fieldErrors.join("; ");
      }
    } else if (typeof data === "string") {
      message = data;
    }

    throw new ApiError(message, response.status, details);
  }

  return data as T;
}

// ----------------------------------------------------------------------
// Specific API Endpoints & Interfaces
// ----------------------------------------------------------------------

export interface BackendOrganisationSummary {
  organisation_id: string;
  organisation_name: string;
  organisation_slug: string;
  organisation_type: string;
  role: string;
  joined_at: string;
}

export interface BackendUserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  full_name: string;
  status: "ACTIVE" | "PENDING" | "SUSPENDED" | "DEACTIVATED";
  roles: string[];
  active_role?: string;
  has_mfa_enabled?: boolean;
  staff_role?: { code: string; name: string; department?: string } | null;
  permissions?: string[];
  is_staff: boolean;
  is_superuser: boolean;
  organisations: BackendOrganisationSummary[];
  date_joined: string;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  status: string;
  message: string;
  code?: string;
  active_role?: string;
  mfa_required?: boolean;
  pre_auth_token?: string;
  email?: string;
  tokens?: {
    access: string;
    refresh: string;
  };
  user?: BackendUserProfile;
}

export interface LogoutResponse {
  status: string;
  message: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  roles?: string[];
}

export interface RegisterResponse {
  status: string;
  message: string;
  user: BackendUserProfile;
}

export interface BackendOrganisation {
  id: string;
  name: string;
  slug: string;
  type: "INDIVIDUAL" | "DEALER_GROUP" | "WORKSHOP" | "FLEET_OPERATOR" | "INTERNAL_OPS";
  jurisdiction: string;
  created_by?: string;
  is_active: boolean;
  user_role: string | null;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface PaginatedOrganisations {
  count: number;
  next: string | null;
  previous: string | null;
  results: BackendOrganisation[];
}

export interface CreateOrganisationPayload {
  name: string;
  type?: "INDIVIDUAL" | "DEALER_GROUP" | "WORKSHOP" | "FLEET_OPERATOR" | "INTERNAL_OPS";
  jurisdiction?: string;
}

export interface BackendOrganisationMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: "OWNER" | "ADMIN" | "MEMBER" | "TECHNICIAN" | "ANALYST";
  is_active: boolean;
  joined_at: string;
}

export interface AddMemberPayload {
  email: string;
  role: "ADMIN" | "MEMBER" | "TECHNICIAN" | "ANALYST";
}

export interface AddMemberResponse {
  status: string;
  message: string;
  member: BackendOrganisationMember;
}

export interface StaffInvitePayload {
  email: string;
  staff_role: "VERIFICATION_OFFICER" | "DISPUTE_MANAGER" | "FINANCE_OFFICER" | "SUPPORT_AGENT" | string;
  first_name?: string;
  last_name?: string;
  department?: string;
}

export interface StaffInviteResponse {
  status: string;
  message: string;
  email: string;
  staff_role: string;
  invite_token?: string | null;
}

export const api = {
  auth: {
    async login(email: string, password: string, code?: string): Promise<LoginResponse> {
      const data = await apiRequest<LoginResponse>("/auth/login/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ email, password, code }),
      });
      if (data?.mfa_required) {
        return data;
      }
      if (!data?.tokens?.access || !data?.tokens?.refresh) {
        throw new ApiError("Authentication failed: both access and refresh tokens are required.", 500);
      }
      tokenStorage.setTokens(data.tokens.access, data.tokens.refresh);
      return data;
    },

    async switchRole(role: string): Promise<{ status: string; message: string; active_role: string; tokens: { access: string; refresh: string } }> {
      const data = await apiRequest<{ status: string; message: string; active_role: string; tokens: { access: string; refresh: string } }>("/auth/switch-role/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ role }),
      });
      if (data?.tokens?.access) {
        tokenStorage.setTokens(data.tokens.access, data.tokens.refresh);
      }
      return data;
    },

    async enrolMfa(): Promise<{ status: string; secret: string; qr_code_uri: string; message: string }> {
      return apiRequest<{ status: string; secret: string; qr_code_uri: string; message: string }>("/auth/mfa/enrol/", {
        method: "POST",
        requiresAuth: true,
      });
    },

    async verifyMfa(code: string, pre_auth_token?: string): Promise<LoginResponse> {
      const data = await apiRequest<LoginResponse>("/auth/mfa/verify/", {
        method: "POST",
        requiresAuth: !pre_auth_token,
        body: JSON.stringify({ code, pre_auth_token }),
      });
      if (data?.tokens?.access && data?.tokens?.refresh) {
        tokenStorage.setTokens(data.tokens.access, data.tokens.refresh);
      }
      return data;
    },

    async staffSetPassword(payload: { token: string; new_password: string }): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>("/auth/staff/set-password/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify(payload),
      });
    },

    async register(payload: RegisterPayload): Promise<RegisterResponse> {
      return apiRequest<RegisterResponse>("/auth/register/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify(payload),
      });
    },

    async logout(): Promise<LogoutResponse> {
      const refreshToken = tokenStorage.getRefreshToken();
      try {
        if (refreshToken) {
          const res = await apiRequest<LogoutResponse>("/auth/logout/", {
            method: "POST",
            requiresAuth: true,
            body: JSON.stringify({ refresh: refreshToken }),
          });
          tokenStorage.clearTokens();
          return res;
        }
      } catch {
        // Even if logout request fails remotely, client credentials must be purged
      } finally {
        tokenStorage.clearTokens();
      }
      return { status: "success", message: "Logged out locally." };
    },

    async verifyEmail(token: string): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>("/auth/verify-email/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ token }),
      });
    },

    async resendVerification(email: string): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>("/auth/resend-verification/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ email }),
      });
    },

    async requestPasswordReset(email: string): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>("/auth/password-reset/request/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ email }),
      });
    },

    async confirmPasswordReset(payload: { token: string; new_password: string }): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>("/auth/password-reset/confirm/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify(payload),
      });
    },
  },

  admin: {
    async inviteStaff(payload: StaffInvitePayload): Promise<StaffInviteResponse> {
      return apiRequest<StaffInviteResponse>("/admin/staff/invite/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },
  },

  users: {
    async getMe(): Promise<BackendUserProfile> {
      return apiRequest<BackendUserProfile>("/users/me/", {
        method: "GET",
        requiresAuth: true,
      });
    },

    async updateMe(payload: {
      first_name?: string;
      last_name?: string;
      phone_number?: string;
    }): Promise<BackendUserProfile> {
      return apiRequest<BackendUserProfile>("/users/me/", {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },
  },

  organisations: {
    async list(): Promise<PaginatedOrganisations> {
      return apiRequest<PaginatedOrganisations>("/organisations/", {
        method: "GET",
        requiresAuth: true,
      });
    },

    async create(payload: CreateOrganisationPayload): Promise<BackendOrganisation> {
      return apiRequest<BackendOrganisation>("/organisations/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async get(id: string): Promise<BackendOrganisation> {
      return apiRequest<BackendOrganisation>(`/organisations/${id}/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async getMembers(orgId: string): Promise<BackendOrganisationMember[]> {
      return apiRequest<BackendOrganisationMember[]>(`/organisations/${orgId}/members/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async addMember(orgId: string, payload: AddMemberPayload): Promise<AddMemberResponse> {
      return apiRequest<AddMemberResponse>(`/organisations/${orgId}/members/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },
  },

  // Phase 2: Seller Onboarding & Verification
  seller: {
    async getMyApplication(): Promise<SellerApplication | null> {
      const res = await apiRequest<{ status: string; application?: SellerApplication | null } | SellerApplication>("/seller/application/", {
        method: "GET",
        requiresAuth: true,
      });
      if (res && typeof res === "object") {
        if ("application" in res) {
          return res.application || null;
        }
        if ("id" in res) {
          return res as SellerApplication;
        }
      }
      return null;
    },

    async saveDraft(payload: SellerApplicationCreateUpdatePayload): Promise<SellerApplication> {
      const res = await apiRequest<{ status: string; application?: SellerApplication } | SellerApplication>("/seller/application/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
      if (res && typeof res === "object" && "application" in res && res.application) {
        return res.application;
      }
      return res as SellerApplication;
    },

    async submit(): Promise<{ message: string; application: SellerApplication }> {
      return apiRequest<{ message: string; application: SellerApplication }>("/seller/application/submit/", {
        method: "POST",
        requiresAuth: true,
      });
    },

    async listAdminApplications(statusFilter?: string): Promise<SellerApplication[]> {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
      const res = await apiRequest<SellerApplication[] | { results: SellerApplication[] }>(
        `/admin/seller-applications/${q}`,
        {
          method: "GET",
          requiresAuth: true,
        }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getAdminApplication(id: string): Promise<SellerApplication> {
      return apiRequest<SellerApplication>(`/admin/seller-applications/${id}/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async reviewApplication(
      id: string,
      payload: {
        action: "APPROVE" | "REJECT" | "approve" | "reject";
        reason?: string;
        rejection_reason?: string;
        admin_notes?: string;
      }
    ): Promise<SellerApplication> {
      const normalizedAction = payload.action.toUpperCase() as "APPROVE" | "REJECT";
      const reasonText = payload.reason || payload.rejection_reason || "";
      const res = await apiRequest<{ status: string; message: string; application: SellerApplication } | SellerApplication>(
        `/admin/seller-applications/${id}/review/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify({
            action: normalizedAction,
            reason: reasonText,
            rejection_reason: reasonText,
            admin_notes: payload.admin_notes,
          }),
        }
      );
      if (res && typeof res === "object" && "application" in res && res.application) {
        return res.application;
      }
      return res as SellerApplication;
    },
  },

  // Phase 2: Vehicle & Parts Catalogue
  catalogue: {
    async getMakes(): Promise<VehicleMake[]> {
      const res = await apiRequest<VehicleMake[] | { results: VehicleMake[] }>("/catalogue/makes/", {
        method: "GET",
        requiresAuth: false,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getModels(makeId?: string): Promise<VehicleModel[]> {
      const q = makeId ? `?make=${encodeURIComponent(makeId)}` : "";
      const res = await apiRequest<VehicleModel[] | { results: VehicleModel[] }>(`/catalogue/models/${q}`, {
        method: "GET",
        requiresAuth: false,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getVariants(modelId?: string): Promise<VehicleVariant[]> {
      const q = modelId ? `?model=${encodeURIComponent(modelId)}` : "";
      const res = await apiRequest<VehicleVariant[] | { results: VehicleVariant[] }>(`/catalogue/variants/${q}`, {
        method: "GET",
        requiresAuth: false,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getCategories(): Promise<PartCategory[]> {
      const res = await apiRequest<PartCategory[] | { results: PartCategory[] }>("/catalogue/categories/", {
        method: "GET",
        requiresAuth: false,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getParts(params?: { category?: string; brand?: string; search?: string }): Promise<PartSummary[]> {
      const query = new URLSearchParams();
      if (params?.category) query.append("category", params.category);
      if (params?.brand) query.append("brand", params.brand);
      if (params?.search) query.append("search", params.search);
      const qs = query.toString() ? `?${query.toString()}` : "";
      const res = await apiRequest<PartSummary[] | { results: PartSummary[] }>(`/catalogue/parts/${qs}`, {
        method: "GET",
        requiresAuth: false,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getPart(id: string): Promise<PartDetail> {
      return apiRequest<PartDetail>(`/catalogue/parts/${id}/`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getPartCompatibilities(partId: string): Promise<PartCompatibilityItem[]> {
      const res = await apiRequest<PartCompatibilityItem[] | { results: PartCompatibilityItem[] }>(
        `/catalogue/parts/${partId}/compatibilities/`,
        {
          method: "GET",
          requiresAuth: false,
        }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async evaluateFitment(partId: string, variantId: string): Promise<FitmentEvaluation> {
      return apiRequest<FitmentEvaluation>("/catalogue/fitment/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ part_id: partId, variant_id: variantId }),
      });
    },
  },

  // Phase 2: Personal Vehicle Garage
  garage: {
    async listVehicles(): Promise<GarageVehicle[]> {
      const res = await apiRequest<GarageVehicle[] | { results: GarageVehicle[] }>("/garage/vehicles/", {
        method: "GET",
        requiresAuth: true,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getVehicle(id: string): Promise<GarageVehicle> {
      return apiRequest<GarageVehicle>(`/garage/vehicles/${id}/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async addVehicle(payload: AddGarageVehiclePayload): Promise<GarageVehicle> {
      return apiRequest<GarageVehicle>("/garage/vehicles/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async updateVehicle(id: string, payload: Partial<AddGarageVehiclePayload>): Promise<GarageVehicle> {
      return apiRequest<GarageVehicle>(`/garage/vehicles/${id}/`, {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async setPrimary(id: string): Promise<GarageVehicle> {
      return apiRequest<GarageVehicle>(`/garage/vehicles/${id}/set-primary/`, {
        method: "POST",
        requiresAuth: true,
      });
    },

    async archiveVehicle(id: string): Promise<void> {
      return apiRequest<void>(`/garage/vehicles/${id}/`, {
        method: "DELETE",
        requiresAuth: true,
      });
    },

    async deleteVehicle(id: string): Promise<void> {
      return this.archiveVehicle(id);
    },
  },

  // Marketplace: Vehicles & Spare Parts Submissions, Approvals & Public Browse
  marketplace: {
    // Buyer Public Browse
    async browseVehicles(params?: Record<string, string>): Promise<MarketplaceVehicleListing[]> {
      const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
      const res = await apiRequest<MarketplaceVehicleListing[] | { results: MarketplaceVehicleListing[] }>(
        `/marketplace/browse/vehicles/${qs}`,
        { method: "GET", requiresAuth: false }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getVehicle(id: string): Promise<MarketplaceVehicleListing> {
      return apiRequest<MarketplaceVehicleListing>(`/marketplace/browse/vehicles/${id}/`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async browseParts(params?: Record<string, string>): Promise<MarketplacePartListing[]> {
      const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
      const res = await apiRequest<MarketplacePartListing[] | { results: MarketplacePartListing[] }>(
        `/marketplace/browse/parts/${qs}`,
        { method: "GET", requiresAuth: false }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getPart(id: string): Promise<MarketplacePartListing> {
      return apiRequest<MarketplacePartListing>(`/marketplace/browse/parts/${id}/`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    // Seller Inventory Management
    async listMyVehicles(status?: string): Promise<MarketplaceVehicleListing[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<MarketplaceVehicleListing[] | { results: MarketplaceVehicleListing[] }>(
        `/marketplace/vehicles/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async createVehicle(payload: CreateVehicleListingPayload): Promise<MarketplaceVehicleListing> {
      return apiRequest<MarketplaceVehicleListing>("/marketplace/vehicles/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async updateVehicle(id: string, payload: Partial<CreateVehicleListingPayload>): Promise<MarketplaceVehicleListing> {
      return apiRequest<MarketplaceVehicleListing>(`/marketplace/vehicles/${id}/`, {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async submitVehicle(id: string): Promise<MarketplaceVehicleListing> {
      const res = await apiRequest<{ listing: MarketplaceVehicleListing }>(
        `/marketplace/vehicles/${id}/submit/`,
        { method: "POST", requiresAuth: true }
      );
      return res.listing;
    },

    async resubmitVehicle(id: string): Promise<MarketplaceVehicleListing> {
      const res = await apiRequest<{ listing: MarketplaceVehicleListing }>(
        `/marketplace/vehicles/${id}/resubmit/`,
        { method: "POST", requiresAuth: true }
      );
      return res.listing;
    },

    async listMyParts(status?: string): Promise<MarketplacePartListing[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<MarketplacePartListing[] | { results: MarketplacePartListing[] }>(
        `/marketplace/parts/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async createPart(payload: CreatePartListingPayload): Promise<MarketplacePartListing> {
      return apiRequest<MarketplacePartListing>("/marketplace/parts/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async updatePart(id: string, payload: Partial<CreatePartListingPayload>): Promise<MarketplacePartListing> {
      return apiRequest<MarketplacePartListing>(`/marketplace/parts/${id}/`, {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async submitPart(id: string): Promise<MarketplacePartListing> {
      const res = await apiRequest<{ listing: MarketplacePartListing }>(
        `/marketplace/parts/${id}/submit/`,
        { method: "POST", requiresAuth: true }
      );
      return res.listing;
    },

    async resubmitPart(id: string): Promise<MarketplacePartListing> {
      const res = await apiRequest<{ listing: MarketplacePartListing }>(
        `/marketplace/parts/${id}/resubmit/`,
        { method: "POST", requiresAuth: true }
      );
      return res.listing;
    },

    async adjustPartStock(id: string, payload: StockAdjustmentPayload): Promise<StockAdjustmentResponse> {
      return apiRequest<StockAdjustmentResponse>(`/marketplace/parts/${id}/stock/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async getPartStockHistory(id: string): Promise<StockMovement[]> {
      const res = await apiRequest<StockMovement[] | { results: StockMovement[] }>(
        `/marketplace/parts/${id}/stock-history/`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async listLowStockParts(status?: string): Promise<MarketplacePartListing[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<MarketplacePartListing[] | { results: MarketplacePartListing[] }>(
        `/marketplace/parts/low-stock/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    // Admin Review Queues
    async listAdminVehicles(status?: string): Promise<MarketplaceVehicleListing[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<MarketplaceVehicleListing[] | { results: MarketplaceVehicleListing[] }>(
        `/marketplace/admin/vehicles/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async reviewVehicle(id: string, payload: ReviewListingPayload): Promise<MarketplaceVehicleListing> {
      const res = await apiRequest<{ listing: MarketplaceVehicleListing }>(
        `/marketplace/admin/vehicles/${id}/review/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
      return res.listing;
    },

    async listAdminParts(status?: string): Promise<MarketplacePartListing[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<MarketplacePartListing[] | { results: MarketplacePartListing[] }>(
        `/marketplace/admin/parts/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async reviewPart(id: string, payload: ReviewListingPayload): Promise<MarketplacePartListing> {
      const res = await apiRequest<{ listing: MarketplacePartListing }>(
        `/marketplace/admin/parts/${id}/review/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
      return res.listing;
    },
  },
};

// ==========================================
// Phase 2 Type Definitions
// ==========================================

export interface SellerApplication {
  id: string;
  user: string;
  user_email: string;
  user_full_name: string;
  organisation?: string | null;
  organisation_name?: string | null;
  business_name: string;
  trading_name?: string;
  business_type: string;
  business_type_display?: string;
  registration_number?: string;
  vat_number?: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  business_address_line1: string;
  business_address_line2?: string;
  business_city: string;
  business_state_province?: string;
  business_postal_code: string;
  business_country: string;
  status: "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";
  status_display?: string;
  rejection_reason?: string;
  submitted_at?: string | null;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  reviewed_by_email?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SellerApplicationCreateUpdatePayload {
  organisation?: string | null;
  business_name: string;
  trading_name?: string;
  business_type?: string;
  registration_number?: string;
  vat_number?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  business_address_line1?: string;
  business_address_line2?: string;
  business_city?: string;
  business_state_province?: string;
  business_postal_code?: string;
  business_country?: string;
}

export interface VehicleMake {
  id: string;
  name: string;
  country_of_origin?: string;
  is_active: boolean;
  models_count?: number;
}

export interface VehicleModel {
  id: string;
  make: string;
  make_name?: string;
  name: string;
  year_start?: number | null;
  year_end?: number | null;
  body_type?: string;
  is_active: boolean;
  variants_count?: number;
}

export interface VehicleVariant {
  id: string;
  model: string;
  model_name?: string;
  make_name?: string;
  name: string;
  display_name?: string;
  year: number;
  engine_code?: string;
  fuel_type: string;
  transmission: string;
  power_bhp?: number | null;
  drivetrain?: string;
  is_active: boolean;
}

export interface PartCategory {
  id: string;
  name: string;
  slug: string;
  description?: string;
  parent?: string | null;
  parent_name?: string | null;
  subcategories?: PartCategory[];
  is_active: boolean;
}

export interface PartCompatibilityItem {
  id: string;
  part: string;
  vehicle_variant: string;
  vehicle_display?: string;
  is_direct_fit: boolean;
  fitment_notes?: string;
  position?: string;
  model_year_from?: number | null;
  model_year_to?: number | null;
}

export interface PartSummary {
  id: string;
  name: string;
  part_number: string;
  category: string;
  category_name?: string;
  brand: string;
  oem_numbers?: string[];
  is_universal: boolean;
  is_active: boolean;
  compatibilities_count?: number;
}

export interface PartDetail extends PartSummary {
  description?: string;
  technical_specs?: Record<string, unknown>;
  primary_image_url?: string;
  compatibilities?: PartCompatibilityItem[];
  created_at: string;
  updated_at: string;
}

export interface FitmentEvaluation {
  outcome: "CONFIRMED_FIT" | "CONDITIONAL_FIT" | "DOES_NOT_FIT" | "UNKNOWN";
  is_compatible: boolean;
  confidence?: string;
  evidence_level?: string;
  reason?: string;
  qualifications?: string;
  notes?: string;
  position?: string;
  details?: Record<string, unknown>;
  vehicle_info?: string;
}

export interface GarageVehicle {
  id: string;
  user: string;
  user_email: string;
  vehicle_variant?: string | null;
  variant_display?: string | null;
  registration_plate?: string;
  vin?: string;
  nickname?: string;
  make: string;
  model: string;
  year: number;
  trim?: string;
  engine_code?: string;
  fuel_type?: string;
  transmission?: string;
  power_bhp?: number | null;
  color?: string;
  current_odometer?: number;
  odometer_unit: string;
  mot_status: string;
  mot_expiry_date?: string | null;
  mot_data_source?: string;
  active_recalls_count: number;
  recalls_data_source?: string;
  ownership_status: string;
  primary_image_url?: string;
  is_primary: boolean;
  is_archived?: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AddGarageVehiclePayload {
  vehicle_variant?: string;
  make?: string;
  model?: string;
  year?: number;
  trim?: string;
  registration_plate?: string;
  vin?: string;
  nickname?: string;
  engine_code?: string;
  fuel_type?: string;
  transmission?: string;
  power_bhp?: number;
  color?: string;
  current_odometer?: number;
  odometer_unit?: string;
  is_primary?: boolean;
}

// ==========================================
// Marketplace Types
// ==========================================

export interface MarketplaceVehicleListing {
  id: string;
  seller?: string;
  seller_name?: string;
  organisation?: string | null;
  organisation_name?: string | null;
  title: string;
  make: string;
  make_name: string;
  model: string;
  model_name: string;
  variant?: string | null;
  variant_name?: string | null;
  variant_details?: VehicleVariant | null;
  year: number;
  registration_number?: string;
  vin?: string;
  masked_vin?: string;
  masked_registration?: string;
  mileage: number;
  fuel_type: string;
  transmission: string;
  body_type?: string;
  price: string | number;
  currency: string;
  condition: string;
  description?: string;
  primary_image_url?: string;
  images?: string[];
  location_city?: string;
  location_postcode?: string;
  status: "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";
  submitted_at?: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
  rejection_reason?: string;
  admin_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface MarketplacePartListing {
  id: string;
  seller?: string;
  seller_name?: string;
  organisation?: string | null;
  organisation_name?: string | null;
  name: string;
  brand: string;
  mpn: string;
  oem_numbers?: string[];
  category: string;
  category_name?: string;
  category_slug?: string;
  description?: string;
  price: string | number;
  currency: string;
  stock_quantity: number;
  low_stock_threshold?: number;
  availability?: "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK";
  condition: string;
  primary_image_url?: string;
  images?: string[];
  compatible_variants?: VehicleVariant[];
  compatibility_notes?: string;
  status: "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";
  submitted_at?: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
  rejection_reason?: string;
  admin_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateVehicleListingPayload {
  title: string;
  make: string;
  model: string;
  variant?: string;
  year: number;
  registration_number?: string;
  vin?: string;
  mileage?: number;
  fuel_type?: string;
  transmission?: string;
  body_type?: string;
  price: number | string;
  currency?: string;
  condition?: string;
  description?: string;
  primary_image_url?: string;
  images?: string[];
  location_city?: string;
  location_postcode?: string;
  organisation?: string | null;
  status?: "DRAFT" | "PENDING_APPROVAL";
}

export interface CreatePartListingPayload {
  name: string;
  brand: string;
  mpn: string;
  oem_numbers?: string[];
  category: string;
  description?: string;
  price: number | string;
  currency?: string;
  stock_quantity?: number;
  low_stock_threshold?: number;
  condition?: string;
  primary_image_url?: string;
  images?: string[];
  compatible_variants?: string[];
  compatibility_notes?: string;
  organisation?: string | null;
  status?: "DRAFT" | "PENDING_APPROVAL";
}

export interface ReviewListingPayload {
  action: "APPROVE" | "REJECT" | "REQUEST_CHANGES";
  rejection_reason?: string;
  admin_notes?: string;
}

export interface StockMovement {
  id: string;
  listing: string;
  delta: number;
  resulting_quantity: number;
  reason: "INITIAL" | "ADJUSTMENT" | "SALE" | "RETURN" | "CORRECTION";
  actor?: string | null;
  actor_name?: string | null;
  note: string;
  created_at: string;
}

export interface StockAdjustmentPayload {
  delta: number;
  reason: "ADJUSTMENT" | "CORRECTION";
  note?: string;
}

export interface StockAdjustmentResponse {
  status: string;
  message: string;
  movement: StockMovement;
  listing: MarketplacePartListing;
}
