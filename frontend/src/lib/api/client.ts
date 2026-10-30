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

export function getBackendOrigin(): string {
  const apiBase = getBaseUrl();
  try {
    const parsed = new URL(apiBase);
    return parsed.origin;
  } catch {
    return "http://127.0.0.1:8000";
  }
}

/**
 * Resolves an image URL:
 * - Passes through http://, https://, data:, and blob: object URLs untouched.
 * - Prefixes relative media paths (/media/...) with the Django backend origin (http://127.0.0.1:8000).
 */
export function resolveMediaUrl(url?: string | null): string {
  if (!url) return "";
  const trimmed = url.trim();
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("data:") ||
    trimmed.startsWith("blob:")
  ) {
    return trimmed;
  }
  const origin = getBackendOrigin();
  const cleanPath = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return `${origin}${cleanPath}`;
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
  const url = endpoint.startsWith("http://") || endpoint.startsWith("https://")
    ? endpoint
    : `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const isFormData = typeof FormData !== "undefined" && restOptions.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(!isFormData ? { "Content-Type": "application/json" } : {}),
    ...(customHeaders as Record<string, string>),
  };
  if (isFormData && headers["Content-Type"]) {
    delete headers["Content-Type"];
  }

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
      const trimmed = data.trim();
      if (
        trimmed.startsWith("<!DOCTYPE") ||
        trimmed.startsWith("<html") ||
        trimmed.includes("<body") ||
        trimmed.includes("Traceback (most recent call last):")
      ) {
        // Sanitize raw Django HTML error tracebacks
        const excMatch = trimmed.match(/<pre class="exception_value">([^<]+)<\/pre>/i);
        const titleMatch = trimmed.match(/<title>([^<]+)<\/title>/i);
        if (excMatch && excMatch[1]) {
          message = `Server Error: ${excMatch[1].replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&").trim()}`;
        } else if (titleMatch && titleMatch[1]) {
          message = `Server Error: ${titleMatch[1].trim()}`;
        } else {
          message = `Server error (${response.status}). The requested operation could not be completed.`;
        }
      } else {
        message = data;
      }
    }

    // Guard against any lingering HTML markup in error messages
    if (typeof message === "string" && message.includes("<")) {
      message = message.replace(/<[^>]*>/g, "").trim();
    }
    if (!message) {
      message = `Server error (${response.status}).`;
    }

    throw new ApiError(message, response.status, details);
  }

  return data as T;
}

export interface PaginatedResponse<T> {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: T[];
}

export async function fetchAllPages<T>(initialEndpoint: string, options: RequestOptions = {}): Promise<T[]> {
  let allItems: T[] = [];
  let currentEndpoint: string | null = initialEndpoint;

  while (currentEndpoint) {
    const res: T[] | PaginatedResponse<T> = await apiRequest<T[] | PaginatedResponse<T>>(currentEndpoint, options);
    if (Array.isArray(res)) {
      allItems = allItems.concat(res);
      break;
    }
    if (res && typeof res === "object" && Array.isArray(res.results)) {
      allItems = allItems.concat(res.results);
      currentEndpoint = res.next || null;
    } else {
      break;
    }
  }

  return allItems;
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
      return fetchAllPages<VehicleMake>("/catalogue/makes/", {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getModels(makeId?: string): Promise<VehicleModel[]> {
      const q = makeId ? `?make=${encodeURIComponent(makeId)}` : "";
      return fetchAllPages<VehicleModel>(`/catalogue/models/${q}`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getVariants(modelId?: string): Promise<VehicleVariant[]> {
      const q = modelId ? `?model=${encodeURIComponent(modelId)}` : "";
      return fetchAllPages<VehicleVariant>(`/catalogue/variants/${q}`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getCategories(): Promise<PartCategory[]> {
      return fetchAllPages<PartCategory>("/catalogue/categories/", {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getParts(params?: { category?: string; brand?: string; search?: string }): Promise<PartSummary[]> {
      const query = new URLSearchParams();
      if (params?.category) query.append("category", params.category);
      if (params?.brand) query.append("brand", params.brand);
      if (params?.search) query.append("search", params.search);
      const qs = query.toString() ? `?${query.toString()}` : "";
      return fetchAllPages<PartSummary>(`/catalogue/parts/${qs}`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getPart(id: string): Promise<PartDetail> {
      return apiRequest<PartDetail>(`/catalogue/parts/${id}/`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getPartCompatibilities(partId: string): Promise<PartCompatibilityItem[]> {
      return fetchAllPages<PartCompatibilityItem>(
        `/catalogue/parts/${partId}/compatibilities/`,
        {
          method: "GET",
          requiresAuth: false,
        }
      );
    },

    async evaluateFitment(partId: string, variantId: string): Promise<FitmentEvaluation> {
      return apiRequest<FitmentEvaluation>("/catalogue/fitment/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ part_id: partId, variant_id: variantId }),
      });
    },

    async listMakes(): Promise<VehicleMake[]> {
      return this.getMakes();
    },

    async listModels(makeId?: string): Promise<VehicleModel[]> {
      return this.getModels(makeId);
    },

    async listVariants(modelId?: string): Promise<VehicleVariant[]> {
      return this.getVariants(modelId);
    },

    async listApplications(status?: string): Promise<VehicleCatalogueApplication[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<VehicleCatalogueApplication[] | { results: VehicleCatalogueApplication[] }>(
        `/catalogue/applications/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async submitApplication(payload: CreateVehicleCatalogueApplicationPayload): Promise<VehicleCatalogueApplication> {
      return apiRequest<VehicleCatalogueApplication>("/catalogue/applications/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async getApplication(id: string): Promise<VehicleCatalogueApplication> {
      return apiRequest<VehicleCatalogueApplication>(`/catalogue/applications/${id}/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async reviewApplication(
      id: string,
      payload: ReviewCatalogueApplicationPayload
    ): Promise<{ status: string; message: string; application: VehicleCatalogueApplication }> {
      return apiRequest<{ status: string; message: string; application: VehicleCatalogueApplication }>(
        `/catalogue/applications/${id}/review/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async listPhotoProposals(status?: string): Promise<CataloguePhotoProposal[]> {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<CataloguePhotoProposal[] | { results: CataloguePhotoProposal[] }>(
        `/catalogue/photo-proposals/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async submitPhotoProposal(payload: CreateCataloguePhotoProposalPayload): Promise<CataloguePhotoProposal> {
      return apiRequest<CataloguePhotoProposal>("/catalogue/photo-proposals/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async reviewPhotoProposal(
      id: string,
      payload: ReviewCataloguePhotoProposalPayload
    ): Promise<{ status: string; message: string; proposal: CataloguePhotoProposal }> {
      return apiRequest<{ status: string; message: string; proposal: CataloguePhotoProposal }>(
        `/catalogue/photo-proposals/${id}/review/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
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

    // Buyer Saved Favourites
    async listFavourites(): Promise<BuyerFavouriteVehicle[]> {
      const res = await apiRequest<BuyerFavouriteVehicle[] | { results: BuyerFavouriteVehicle[] }>(
        "/marketplace/favourites/",
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async addFavourite(vehicleId: string): Promise<BuyerFavouriteVehicle> {
      return apiRequest<BuyerFavouriteVehicle>("/marketplace/favourites/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ vehicle_id: vehicleId }),
      });
    },

    async removeFavourite(idOrVehicleId: string): Promise<void> {
      return apiRequest<void>(`/marketplace/favourites/${idOrVehicleId}/`, {
        method: "DELETE",
        requiresAuth: true,
      });
    },

    // Buyer Saved Part Favourites
    async listPartFavourites(): Promise<BuyerFavouritePart[]> {
      const res = await apiRequest<BuyerFavouritePart[] | { results: BuyerFavouritePart[] }>(
        "/marketplace/favourites/parts/",
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async addPartFavourite(partId: string): Promise<BuyerFavouritePart> {
      return apiRequest<BuyerFavouritePart>("/marketplace/favourites/parts/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ part_id: partId }),
      });
    },

    async removePartFavourite(idOrPartId: string): Promise<void> {
      return apiRequest<void>(`/marketplace/favourites/parts/${idOrPartId}/`, {
        method: "DELETE",
        requiresAuth: true,
      });
    },


    async browsePartsPaginated(params?: BrowsePartsParams): Promise<PaginatedPartListResponse> {
      const cleanParams: Record<string, string> = {};
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          if (v !== undefined && v !== null && v !== "") {
            cleanParams[k] = String(v);
          }
        }
      }
      const qs = Object.keys(cleanParams).length > 0 ? `?${new URLSearchParams(cleanParams).toString()}` : "";
      const res = await apiRequest<PaginatedPartListResponse>(
        `/marketplace/browse/parts/${qs}`,
        { method: "GET", requiresAuth: Boolean(cleanParams.fits_vehicle) }
      );
      return res;
    },

    async browseParts(params?: BrowsePartsParams): Promise<MarketplacePartListing[]> {
      const res = await this.browsePartsPaginated(params);
      return res.results || [];
    },

    async getPart(id: string, params?: Record<string, string>): Promise<MarketplacePartListing> {
      const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
      return apiRequest<MarketplacePartListing>(`/marketplace/browse/parts/${id}/${qs}`, {
        method: "GET",
        requiresAuth: Boolean(params?.fits_vehicle),
      });
    },

    // Real Image Upload Management (Files from Seller's Computer)
    async uploadImage(
      file: File,
      options?: { listingType?: "vehicle" | "part" | "catalogue"; listingId?: string }
    ): Promise<UploadedImageResponse> {
      const formData = new FormData();
      formData.append("file", file);
      if (options?.listingType) formData.append("listing_type", options.listingType);
      if (options?.listingId) formData.append("listing_id", options.listingId);

      return apiRequest<UploadedImageResponse>("/marketplace/upload-image/", {
        method: "POST",
        requiresAuth: true,
        body: formData,
      });
    },

    async uploadMultipleImages(
      files: File[],
      options?: { listingType?: "vehicle" | "part" | "catalogue"; listingId?: string }
    ): Promise<{ status: string; count?: number; images: UploadedImageResponse[] }> {
      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));
      if (options?.listingType) formData.append("listing_type", options.listingType);
      if (options?.listingId) formData.append("listing_id", options.listingId);

      return apiRequest<{ status: string; count?: number; images: UploadedImageResponse[] }>("/marketplace/upload-image/", {
        method: "POST",
        requiresAuth: true,
        body: formData,
      });
    },

    async deleteUploadedImage(url: string): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>("/marketplace/upload-image/", {
        method: "DELETE",
        requiresAuth: true,
        body: JSON.stringify({ url }),
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

    // Direct Buyer-Seller Enquiries
    async enquireVehicle(listingId: string, payload: CreateVehicleEnquiryPayload): Promise<VehicleEnquiry> {
      return apiRequest<VehicleEnquiry>(`/marketplace/vehicles/${listingId}/enquire/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async listSellerEnquiries(params?: { status?: string; listing_id?: string }): Promise<VehicleEnquiry[]> {
      const searchParams = new URLSearchParams();
      if (params?.status && params.status !== "ALL") searchParams.set("status", params.status);
      if (params?.listing_id) searchParams.set("listing_id", params.listing_id);
      const qs = searchParams.toString() ? `?${searchParams.toString()}` : "";
      const res = await apiRequest<VehicleEnquiry[] | { results: VehicleEnquiry[] }>(
        `/marketplace/seller/enquiries/${qs}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async updateSellerEnquiry(id: string, payload: UpdateVehicleEnquiryPayload): Promise<VehicleEnquiry> {
      return apiRequest<VehicleEnquiry>(`/marketplace/seller/enquiries/${id}/`, {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async listBuyerEnquiries(): Promise<VehicleEnquiry[]> {
      const res = await apiRequest<VehicleEnquiry[] | { results: VehicleEnquiry[] }>(
        `/marketplace/buyer/enquiries/`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
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

    async getPartPriceHistory(id: string): Promise<PriceChange[]> {
      const res = await apiRequest<PriceChange[] | { results: PriceChange[] }>(
        `/marketplace/parts/${id}/price-history/`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getCataloguePartOffers(cataloguePartId: string): Promise<CataloguePartOffer[]> {
      const res = await apiRequest<CataloguePartOffer[] | { results: CataloguePartOffer[] }>(
        `/marketplace/browse/parts/catalogue/${cataloguePartId}/offers/`,
        { method: "GET", requiresAuth: false }
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

    // Tax Options & Checkout
    async getGstOptions(): Promise<GSTOptionsResponse> {
      return apiRequest<GSTOptionsResponse>("/marketplace/tax/gst-options/", {
        method: "GET",
        requiresAuth: false,
      });
    },

    async getPaymentMethods(params?: {
      country?: string;
      currency?: string;
      amount?: number | string;
    }): Promise<AvailablePaymentMethodsResponse> {
      const query = new URLSearchParams();
      if (params?.country) query.set("country", params.country);
      if (params?.currency) query.set("currency", params.currency);
      if (params?.amount !== undefined) query.set("amount", String(params.amount));
      const qs = query.toString();
      return apiRequest<AvailablePaymentMethodsResponse>(
        `/marketplace/orders/payment-methods/${qs ? `?${qs}` : ""}`,
        {
          method: "GET",
          requiresAuth: false,
        }
      );
    },

    async checkout(payload: OrderCheckoutPayload): Promise<{
      status: string;
      message: string;
      replayed?: boolean;
      order: PlatformOrder;
      payment_session?: PaymentSessionResponse;
    }> {
      const customHeaders: Record<string, string> = {};
      if (payload.idempotency_key) {
        customHeaders["Idempotency-Key"] = payload.idempotency_key;
      }
      return apiRequest<{
        status: string;
        message: string;
        replayed?: boolean;
        order: PlatformOrder;
        payment_session?: PaymentSessionResponse;
      }>("/marketplace/orders/checkout/", {
        method: "POST",
        requiresAuth: true,
        headers: customHeaders,
        body: JSON.stringify(payload),
      });
    },

    async calculateCheckout(payload: OrderCheckoutPayload): Promise<Record<string, unknown>> {
      return apiRequest<Record<string, unknown>>("/marketplace/orders/calculate/", {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ ...payload, preview_only: true }),
      });
    },

    async createPaymentSession(identifier: string): Promise<{
      status: string;
      order_number: string;
      payment_session: PaymentSessionResponse;
    }> {
      return apiRequest<{
        status: string;
        order_number: string;
        payment_session: PaymentSessionResponse;
      }>(`/marketplace/orders/${identifier}/payment/create/`, {
        method: "POST",
        requiresAuth: true,
      });
    },

    async verifyPayment(
      identifier: string,
      payload: PaymentVerifyPayload
    ): Promise<PaymentVerifyResponse> {
      return apiRequest<PaymentVerifyResponse>(
        `/marketplace/orders/${identifier}/payment/verify/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async simulateTestPayment(identifier: string): Promise<{
      status: string;
      message?: string;
      error?: string;
      already_paid?: boolean;
      payment_reference?: string;
      payment_status?: string;
      order?: PlatformOrder;
      extra?: Record<string, unknown>;
    }> {
      return apiRequest<{
        status: string;
        message?: string;
        error?: string;
        already_paid?: boolean;
        payment_reference?: string;
        payment_status?: string;
        order?: PlatformOrder;
        extra?: Record<string, unknown>;
      }>(`/marketplace/orders/${identifier}/payment/simulate/`, {
        method: "POST",
        requiresAuth: true,
      });
    },

    async cancelPayment(
      identifier: string,
      reason?: string
    ): Promise<{
      status: string;
      message: string;
      order?: PlatformOrder;
      error?: string;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        order?: PlatformOrder;
        error?: string;
      }>(`/marketplace/orders/${identifier}/payment/cancel/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ reason }),
      });
    },

    async updateCODCollection(
      identifier: string,
      payload: CODCollectionUpdatePayload
    ): Promise<{
      status: string;
      message: string;
      order: PlatformOrder;
      details: Record<string, unknown>;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        order: PlatformOrder;
        details: Record<string, unknown>;
      }>(`/marketplace/orders/${identifier}/cod-collection/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async getOrderPaymentDetail(identifier: string): Promise<OrderPaymentDetailResponse> {
      return apiRequest<OrderPaymentDetailResponse>(
        `/marketplace/orders/${identifier}/payment/`,
        {
          method: "GET",
          requiresAuth: true,
        }
      );
    },

    async listOrders(): Promise<PlatformOrder[]> {
      const res = await apiRequest<PlatformOrder[] | { results: PlatformOrder[] }>("/marketplace/orders/", {
        method: "GET",
        requiresAuth: true,
      });
      return Array.isArray(res) ? res : res.results || [];
    },

    async getOrder(identifier: string): Promise<PlatformOrder> {
      return apiRequest<PlatformOrder>(`/marketplace/orders/${identifier}/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async cancelBuyerOrder(identifier: string): Promise<{
      status: string;
      message: string;
      order: PlatformOrder;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        order: PlatformOrder;
      }>(`/marketplace/orders/${identifier}/cancel/`, {
        method: "POST",
        requiresAuth: true,
      });
    },

    async listSellerOrders(status?: string, search?: string): Promise<SellerOrder[]> {
      const query = new URLSearchParams();
      if (status && status !== "ALL") query.set("status", status);
      if (search) query.set("search", search);
      const qs = query.toString();
      const res = await apiRequest<SellerOrder[] | { results: SellerOrder[] }>(
        `/marketplace/seller/orders/${qs ? `?${qs}` : ""}`,
        {
          method: "GET",
          requiresAuth: true,
        }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getSellerOrder(identifier: string): Promise<SellerOrder> {
      return apiRequest<SellerOrder>(`/marketplace/seller/orders/${identifier}/`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async updateSellerOrderStatus(
      identifier: string,
      status: string,
      notes?: string
    ): Promise<{
      status: string;
      message: string;
      order: SellerOrder;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        order: SellerOrder;
      }>(`/marketplace/seller/orders/${identifier}/status/`, {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify({ status, notes }),
      });
    },

    // Logistics, Shipping & Order Tracking
    async getAvailableCarriers(country?: string): Promise<AvailableCarriersResponse> {
      const q = country ? `?country=${encodeURIComponent(country)}` : "";
      return apiRequest<AvailableCarriersResponse>(`/marketplace/logistics/carriers/${q}`, {
        method: "GET",
        requiresAuth: false,
      });
    },

    async listSellerOrderShipments(orderIdentifier: string): Promise<PlatformShipment[]> {
      const res = await apiRequest<PlatformShipment[] | { results: PlatformShipment[] }>(
        `/marketplace/seller/orders/${orderIdentifier}/shipments/`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async createShipment(
      orderIdentifier: string,
      payload: CreateShipmentPayload
    ): Promise<{
      status: string;
      message: string;
      shipment: PlatformShipment;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        shipment: PlatformShipment;
      }>(`/marketplace/seller/orders/${orderIdentifier}/shipments/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async getSellerShipment(shipmentIdentifier: string): Promise<PlatformShipment> {
      return apiRequest<PlatformShipment>(
        `/marketplace/seller/shipments/${shipmentIdentifier}/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async updateShipmentStatus(
      shipmentIdentifier: string,
      payload: UpdateShipmentStatusPayload
    ): Promise<{
      status: string;
      message: string;
      shipment: PlatformShipment;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        shipment: PlatformShipment;
      }>(`/marketplace/seller/shipments/${shipmentIdentifier}/status/`, {
        method: "PATCH",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async addTrackingEvent(
      shipmentIdentifier: string,
      payload: CreateTrackingEventPayload
    ): Promise<{
      status: string;
      message: string;
      event: PlatformTrackingEvent;
      shipment: PlatformShipment;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        event: PlatformTrackingEvent;
        shipment: PlatformShipment;
      }>(`/marketplace/seller/shipments/${shipmentIdentifier}/events/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async listBuyerOrderShipments(orderIdentifier: string): Promise<PlatformShipment[]> {
      const res = await apiRequest<PlatformShipment[] | { results: PlatformShipment[] }>(
        `/marketplace/buyer/orders/${orderIdentifier}/shipments/`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async trackShipment(trackingNumber: string): Promise<PlatformShipment> {
      return apiRequest<PlatformShipment>(
        `/marketplace/shipments/track/${encodeURIComponent(trackingNumber)}/`,
        { method: "GET", requiresAuth: true }
      );
    },

    // Returns, Refunds & Dispute Management
    async getReturnEligibility(orderIdentifier: string): Promise<OrderReturnEligibilityResponse> {
      return apiRequest<OrderReturnEligibilityResponse>(
        `/marketplace/buyer/orders/${orderIdentifier}/return-eligibility/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async createReturnRequest(
      orderIdentifier: string,
      payload: CreateReturnRequestPayload
    ): Promise<{
      status: string;
      message: string;
      return_request: PlatformReturnRequest;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        return_request: PlatformReturnRequest;
      }>(`/marketplace/buyer/orders/${orderIdentifier}/returns/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async listBuyerReturns(type?: string, status?: string): Promise<PlatformReturnRequest[]> {
      const q = new URLSearchParams();
      if (type && type !== "ALL") q.set("type", type);
      if (status && status !== "ALL") q.set("status", status);
      const qs = q.toString();
      const res = await apiRequest<PlatformReturnRequest[] | { results: PlatformReturnRequest[] }>(
        `/marketplace/buyer/returns/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getBuyerReturn(identifier: string): Promise<PlatformReturnRequest> {
      return apiRequest<PlatformReturnRequest>(
        `/marketplace/buyer/returns/${identifier}/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async cancelBuyerReturn(identifier: string): Promise<{
      status: string;
      message: string;
      return_request: PlatformReturnRequest;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        return_request: PlatformReturnRequest;
      }>(`/marketplace/buyer/returns/${identifier}/cancel/`, {
        method: "POST",
        requiresAuth: true,
      });
    },

    async listSellerReturns(status?: string, type?: string): Promise<PlatformReturnRequest[]> {
      const q = new URLSearchParams();
      if (status && status !== "ALL") q.set("status", status);
      if (type && type !== "ALL") q.set("type", type);
      const qs = q.toString();
      const res = await apiRequest<PlatformReturnRequest[] | { results: PlatformReturnRequest[] }>(
        `/marketplace/seller/returns/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getSellerReturn(identifier: string): Promise<PlatformReturnRequest> {
      return apiRequest<PlatformReturnRequest>(
        `/marketplace/seller/returns/${identifier}/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async reviewSellerReturn(
      identifier: string,
      payload: ReviewReturnRequestPayload
    ): Promise<{
      status: string;
      message: string;
      return_request: PlatformReturnRequest;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        return_request: PlatformReturnRequest;
      }>(`/marketplace/seller/returns/${identifier}/review/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async completeSellerReturn(
      identifier: string,
      notes?: string
    ): Promise<{
      status: string;
      message: string;
      return_request: PlatformReturnRequest;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        return_request: PlatformReturnRequest;
      }>(`/marketplace/seller/returns/${identifier}/complete/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ notes }),
      });
    },

    async createDispute(
      orderIdentifier: string,
      payload: CreateDisputePayload
    ): Promise<{
      status: string;
      message: string;
      dispute: PlatformDispute;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        dispute: PlatformDispute;
      }>(`/marketplace/buyer/orders/${orderIdentifier}/disputes/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async listBuyerDisputes(): Promise<PlatformDispute[]> {
      const res = await apiRequest<PlatformDispute[] | { results: PlatformDispute[] }>(
        "/marketplace/buyer/disputes/",
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async listSellerDisputes(): Promise<PlatformDispute[]> {
      const res = await apiRequest<PlatformDispute[] | { results: PlatformDispute[] }>(
        "/marketplace/seller/disputes/",
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getDispute(identifier: string): Promise<PlatformDispute> {
      return apiRequest<PlatformDispute>(
        `/marketplace/disputes/${identifier}/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async addDisputeMessage(
      identifier: string,
      payload: CreateDisputeMessagePayload
    ): Promise<{
      status: string;
      message: string;
      event: PlatformDisputeEvent;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        event: PlatformDisputeEvent;
      }>(`/marketplace/disputes/${identifier}/messages/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async getOrderRefundSummary(orderIdentifier: string): Promise<OrderRefundSummary> {
      return apiRequest<OrderRefundSummary>(
        `/marketplace/orders/${orderIdentifier}/refund-summary/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async createAdminRefund(
      orderIdentifier: string,
      payload: CreateAdminRefundPayload
    ): Promise<{
      status: string;
      message: string;
      refund: PlatformRefund;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        refund: PlatformRefund;
      }>(`/marketplace/admin/orders/${orderIdentifier}/refund/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    async listAdminRefunds(status?: string): Promise<PlatformRefund[]> {
      const q = status && status !== "ALL" ? `?status=${encodeURIComponent(status)}` : "";
      const res = await apiRequest<PlatformRefund[] | { results: PlatformRefund[] }>(
        `/marketplace/admin/refunds/${q}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async processAdminRefund(
      identifier: string,
      gatewayReference?: string,
      notes?: string
    ): Promise<{
      status: string;
      message: string;
      refund: PlatformRefund;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        refund: PlatformRefund;
      }>(`/marketplace/admin/refunds/${identifier}/process/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify({ gateway_reference: gatewayReference, notes }),
      });
    },

    async listAdminDisputes(status?: string, category?: string): Promise<PlatformDispute[]> {
      const q = new URLSearchParams();
      if (status && status !== "ALL") q.set("status", status);
      if (category && category !== "ALL") q.set("category", category);
      const qs = q.toString();
      const res = await apiRequest<PlatformDispute[] | { results: PlatformDispute[] }>(
        `/marketplace/admin/disputes/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async updateAdminDisputeStatus(
      identifier: string,
      payload: UpdateDisputeStatusPayload
    ): Promise<{
      status: string;
      message: string;
      dispute: PlatformDispute;
    }> {
      return apiRequest<{
        status: string;
        message: string;
        dispute: PlatformDispute;
      }>(`/marketplace/admin/disputes/${identifier}/status/`, {
        method: "POST",
        requiresAuth: true,
        body: JSON.stringify(payload),
      });
    },

    // Aliases for compatibility across components
    async listSellerReturnRequests(params?: { status?: string; type?: string }): Promise<{ status: string; return_requests: PlatformReturnRequest[] }> {
      const list = await this.listSellerReturns(params?.status, params?.type);
      return { status: "success", return_requests: list };
    },

    async reviewSellerReturnRequest(
      identifier: string,
      payload: ReviewReturnRequestPayload
    ): Promise<{ status: string; message: string; return_request: PlatformReturnRequest }> {
      return this.reviewSellerReturn(identifier, payload);
    },

    async completeSellerReturnRequest(
      identifier: string,
      payload?: { return_tracking_number?: string; notes?: string }
    ): Promise<{ status: string; message: string; return_request: PlatformReturnRequest }> {
      return this.completeSellerReturn(identifier, payload?.return_tracking_number || payload?.notes);
    },

    async getDisputeDetail(
      identifier: string
    ): Promise<{ status: string; dispute: PlatformDispute; events: PlatformDisputeEvent[] }> {
      const dispute = await this.getDispute(identifier);
      return { status: "success", dispute, events: dispute.events || [] };
    },

    async postDisputeMessage(
      identifier: string,
      payload: { message: string; attachments?: string[]; evidence_urls?: string[] }
    ): Promise<{ status: string; message: string; event: PlatformDisputeEvent }> {
      return this.addDisputeMessage(identifier, {
        message: payload.message,
        attachments: payload.attachments || payload.evidence_urls,
      });
    },

    // Reviews, Ratings & Seller Reputation (Task 4)
    async getPartReviews(
      listingId: string,
      params?: { page?: number; rating?: number; page_size?: number }
    ): Promise<{ count: number; next: string | null; previous: string | null; results: PlatformProductReview[]; summary: ProductRatingSummary }> {
      const q = new URLSearchParams();
      if (params?.page) q.set("page", String(params.page));
      if (params?.rating) q.set("rating", String(params.rating));
      if (params?.page_size) q.set("page_size", String(params.page_size));
      const qs = q.toString();
      return apiRequest<{ count: number; next: string | null; previous: string | null; results: PlatformProductReview[]; summary: ProductRatingSummary }>(
        `/marketplace/browse/parts/${listingId}/reviews/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: false }
      );
    },

    async getPartRatingSummary(listingId: string): Promise<ProductRatingSummary> {
      const res = await this.getPartReviews(listingId);
      return res.summary;
    },

    async getOrderReviewEligibility(orderIdentifier: string): Promise<OrderReviewEligibilityResponse> {
      return apiRequest<OrderReviewEligibilityResponse>(
        `/marketplace/buyer/orders/${orderIdentifier}/review-eligibility/`,
        { method: "GET", requiresAuth: true }
      );
    },

    async createProductReview(
      orderIdentifier: string,
      payload: CreateProductReviewPayload
    ): Promise<PlatformProductReview> {
      return apiRequest<PlatformProductReview>(
        `/marketplace/buyer/orders/${orderIdentifier}/reviews/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async updateProductReview(
      reviewId: string,
      payload: { rating?: number; title?: string; comment?: string }
    ): Promise<PlatformProductReview> {
      return apiRequest<PlatformProductReview>(
        `/marketplace/reviews/${reviewId}/`,
        {
          method: "PATCH",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async deleteProductReview(reviewId: string): Promise<{ message: string }> {
      return apiRequest<{ message: string }>(
        `/marketplace/reviews/${reviewId}/`,
        { method: "DELETE", requiresAuth: true }
      );
    },

    async replyToProductReview(reviewId: string, reply: string): Promise<PlatformProductReview> {
      return apiRequest<PlatformProductReview>(
        `/marketplace/reviews/${reviewId}/reply/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify({ reply }),
        }
      );
    },

    async reportProductReview(
      reviewId: string,
      payload: { reason: ReviewReportReason; details?: string }
    ): Promise<{ message: string; report_id: string }> {
      return apiRequest<{ message: string; report_id: string }>(
        `/marketplace/reviews/${reviewId}/report/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async voteHelpfulReview(reviewId: string): Promise<{ has_voted: boolean; helpful_votes: number }> {
      return apiRequest<{ has_voted: boolean; helpful_votes: number }>(
        `/marketplace/reviews/${reviewId}/helpful/`,
        { method: "POST", requiresAuth: true }
      );
    },

    async voteReviewHelpful(reviewId: string): Promise<{ has_voted: boolean; helpful_votes: number; helpful_count: number }> {
      const res = await this.voteHelpfulReview(reviewId);
      return { ...res, helpful_count: res.helpful_votes };
    },

    async reportReview(
      reviewId: string,
      payload: { reason: ReviewReportReason; details?: string }
    ): Promise<{ message: string; report_id: string }> {
      return this.reportProductReview(reviewId, payload);
    },

    async listBuyerReviews(): Promise<PlatformProductReview[]> {
      const res = await apiRequest<PlatformProductReview[] | { results: PlatformProductReview[] }>(
        `/marketplace/buyer/reviews/`,
        { method: "GET", requiresAuth: true }
      );
      return Array.isArray(res) ? res : res.results || [];
    },

    async getSellerReputation(sellerId: string): Promise<SellerReputationSummary> {
      return apiRequest<SellerReputationSummary>(
        `/marketplace/sellers/${sellerId}/reputation/`,
        { method: "GET", requiresAuth: false }
      );
    },

    async listSellerReviews(params?: {
      status?: string;
      rating?: number;
      has_reply?: boolean;
      page?: number;
    }): Promise<{ count: number; results: PlatformProductReview[]; reputation: SellerReputationSummary }> {
      const q = new URLSearchParams();
      if (params?.status && params.status !== "ALL") q.set("status", params.status);
      if (params?.rating) q.set("rating", String(params.rating));
      if (params?.has_reply !== undefined) q.set("has_reply", String(params.has_reply));
      if (params?.page) q.set("page", String(params.page));
      const qs = q.toString();
      return apiRequest<{ count: number; results: PlatformProductReview[]; reputation: SellerReputationSummary }>(
        `/marketplace/seller/reviews/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: true }
      );
    },

    async createSellerRating(payload: CreateSellerRatingPayload): Promise<PlatformSellerReview> {
      return apiRequest<PlatformSellerReview>(
        `/marketplace/seller-ratings/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async replyToSellerReview(reviewId: string, reply: string): Promise<PlatformSellerReview> {
      return apiRequest<PlatformSellerReview>(
        `/marketplace/seller-ratings/${reviewId}/reply/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify({ reply }),
        }
      );
    },

    async listAdminReviews(params?: { status?: string; search?: string; rating?: number }): Promise<PlatformProductReview[] & { results: PlatformProductReview[] }> {
      const q = new URLSearchParams();
      if (params?.status && params.status !== "ALL") q.set("status", params.status);
      if (params?.search) q.set("search", params.search);
      if (params?.rating) q.set("rating", String(params.rating));
      const qs = q.toString();
      const res = await apiRequest<PlatformProductReview[] | { results: PlatformProductReview[] }>(
        `/marketplace/admin/reviews/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: true }
      );
      const arr = Array.isArray(res) ? res : res.results || [];
      (arr as unknown as { results: PlatformProductReview[] }).results = arr;
      return arr as PlatformProductReview[] & { results: PlatformProductReview[] };
    },

    async moderateAdminReview(
      reviewId: string,
      actionOrPayload:
        | "APPROVE"
        | "FLAG"
        | "HIDE"
        | "REJECT"
        | "DELETE"
        | { action: "APPROVE" | "FLAG" | "HIDE" | "REJECT" | "DELETE"; admin_notes?: string },
      admin_notes?: string
    ): Promise<{ message: string; review: PlatformProductReview }> {
      const payload =
        typeof actionOrPayload === "string"
          ? {
              action: actionOrPayload === "REJECT" ? "HIDE" : actionOrPayload,
              admin_notes,
            }
          : {
              ...actionOrPayload,
              action: actionOrPayload.action === "REJECT" ? "HIDE" : actionOrPayload.action,
            };
      return apiRequest<{ message: string; review: PlatformProductReview }>(
        `/marketplace/admin/reviews/${reviewId}/moderate/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },

    async listAdminReviewReports(params?: { status?: string }): Promise<PlatformReviewReport[] & { results: PlatformReviewReport[] }> {
      const q = new URLSearchParams();
      if (params?.status && params.status !== "ALL") q.set("status", params.status);
      const qs = q.toString();
      const res = await apiRequest<PlatformReviewReport[] | { results: PlatformReviewReport[] }>(
        `/marketplace/admin/review-reports/${qs ? `?${qs}` : ""}`,
        { method: "GET", requiresAuth: true }
      );
      const arr = Array.isArray(res) ? res : res.results || [];
      (arr as unknown as { results: PlatformReviewReport[] }).results = arr;
      return arr as PlatformReviewReport[] & { results: PlatformReviewReport[] };
    },

    async resolveAdminReviewReport(
      reportId: string,
      payload: { action: "DISMISS" | "HIDE_REVIEW" | "DELETE_REVIEW"; admin_notes?: string }
    ): Promise<{ message: string; report: PlatformReviewReport }> {
      return apiRequest<{ message: string; report: PlatformReviewReport }>(
        `/marketplace/admin/review-reports/${reportId}/resolve/`,
        {
          method: "POST",
          requiresAuth: true,
          body: JSON.stringify(payload),
        }
      );
    },
  },

  notifications: {
    async list(params?: { unread?: boolean; event_type?: string; page?: number }): Promise<PaginatedNotificationsResponse> {
      const query = new URLSearchParams();
      if (params?.unread) query.set("unread", "true");
      if (params?.event_type) query.set("event_type", params.event_type);
      if (params?.page) query.set("page", String(params.page));
      const qs = query.toString();
      return apiRequest<PaginatedNotificationsResponse>(`/notifications/${qs ? `?${qs}` : ""}`, {
        method: "GET",
        requiresAuth: true,
      });
    },

    async getUnreadCount(): Promise<number> {
      const data = await apiRequest<{ status: string; unread_count: number }>("/notifications/unread-count/", {
        method: "GET",
        requiresAuth: true,
      });
      return data.unread_count;
    },

    async markRead(id: string): Promise<PlatformNotification> {
      const data = await apiRequest<{ status: string; message: string; notification: PlatformNotification }>(
        `/notifications/${id}/read/`,
        { method: "POST", requiresAuth: true }
      );
      return data.notification;
    },

    async markAllRead(): Promise<number> {
      const data = await apiRequest<{ status: string; message: string; updated_count: number }>("/notifications/read-all/", {
        method: "POST",
        requiresAuth: true,
      });
      return data.updated_count;
    },

    async delete(id: string): Promise<{ status: string; message: string }> {
      return apiRequest<{ status: string; message: string }>(`/notifications/${id}/`, {
        method: "DELETE",
        requiresAuth: true,
      });
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
  requested_roles?: string[];
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
  requested_roles?: string[];
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
  image_url?: string;
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

export interface VehicleCatalogueApplication {
  id: string;
  seller: string;
  seller_name: string;
  make?: string | null;
  make_name: string;
  model_name: string;
  year_start: number;
  year_end?: number | null;
  variant_name?: string;
  year?: number | null;
  fuel_type?: string;
  transmission?: string;
  body_type?: string;
  engine_code?: string;
  power_bhp?: number | null;
  engine_capacity_cc?: number | null;
  primary_image_url?: string;
  images?: string[];
  notes?: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";
  rejection_reason?: string;
  admin_notes?: string;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  created_model?: string | null;
  created_model_name?: string | null;
  created_variant?: string | null;
  created_variant_display?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateVehicleCatalogueApplicationPayload {
  make?: string | null;
  make_name: string;
  model_name: string;
  year_start: number;
  year_end?: number | null;
  variant_name?: string;
  year?: number | null;
  fuel_type?: string;
  transmission?: string;
  body_type?: string;
  engine_code?: string;
  power_bhp?: number | null;
  engine_capacity_cc?: number | null;
  primary_image_url?: string;
  images?: string[];
  notes?: string;
}

export interface ReviewCatalogueApplicationPayload {
  action: "APPROVE" | "REJECT" | "REQUEST_CHANGES";
  rejection_reason?: string;
  admin_notes?: string;
}

export interface CataloguePhotoProposal {
  id: string;
  model: string;
  model_name: string;
  make_name: string;
  current_image_url?: string;
  seller: string;
  seller_name: string;
  proposed_image_url: string;
  notes?: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";
  rejection_reason?: string;
  admin_notes?: string;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateCataloguePhotoProposalPayload {
  model: string;
  proposed_image_url: string;
  notes?: string;
}

export interface ReviewCataloguePhotoProposalPayload {
  action: "APPROVE" | "REJECT";
  rejection_reason?: string;
  admin_notes?: string;
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
  mpn?: string;
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
  seller_info?: SellerPublicInfo;
  submitted_at?: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
  rejection_reason?: string;
  admin_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface BuyerFavouriteVehicle {
  id: string;
  vehicle_id: string;
  vehicle: MarketplaceVehicleListing;
  is_available: boolean;
  created_at: string;
}

export interface BuyerFavouritePart {
  id: string;
  part_id: string;
  part: MarketplacePartListing;
  is_available: boolean;
  created_at: string;
}


export interface FitmentVerificationItem {
  variant_id: string;
  display_name: string;
  status: "VERIFIED" | "CONDITIONAL" | "CONFLICT" | "SELLER_CLAIMED" | "UNKNOWN";
  qualifications: string;
  source: "CATALOGUE" | "SELLER" | "NONE";
}

export interface FitmentSummary {
  verified: number;
  conditional: number;
  seller_claimed: number;
  conflict: number;
}

export interface BuyerPartFitment {
  status: "VERIFIED" | "CONDITIONAL" | "CONFLICT" | "SELLER_CLAIMED" | "UNKNOWN";
  qualifications: string;
  source: "CATALOGUE" | "SELLER" | "NONE";
}

export interface TaxBreakdown {
  price_before_gst: string | number;
  gst_rate: string | number;
  gst_amount: string | number;
  total_price: string | number;
  tax_type?: "INTRA_STATE" | "INTER_STATE" | "NONE";
  is_interstate?: boolean;
  place_of_supply?: string;
  seller_state?: string;
  cgst_rate?: string | number;
  cgst_amount?: string | number;
  sgst_rate?: string | number;
  sgst_amount?: string | number;
  igst_rate?: string | number;
  igst_amount?: string | number;
}

export interface HsnClassificationOption {
  hsn_code: string;
  description: string;
  schedule: string;
  standard_rate: string;
  allowed_rates: string[];
  permitted_rates?: string[];
  is_verified: boolean;
  legal_reference: string;
  notes: string;
}

export interface GSTOptionsResponse {
  status: string;
  count: number;
  options?: HsnClassificationOption[];
  hsn_options: HsnClassificationOption[];
  standard_slabs: string[];
}

export interface OrderCheckoutItemPayload {
  listing_id: string;
  quantity: number;
}

export interface OrderCheckoutPayload {
  items: OrderCheckoutItemPayload[];
  place_of_supply?: string;
  currency?: string;
  payment_method?: "ONLINE" | "COD";
  preview_only?: boolean;
  expected_total_amount?: string | number;
  idempotency_key?: string;
  shipping_name?: string;
  shipping_phone?: string;
  shipping_address_line1?: string;
  shipping_address_line2?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_postal_code?: string;
  shipping_country?: string;
}

export interface PlatformOrderItem {
  id: string;
  listing?: string | null;
  listing_id?: string | null;
  seller_id?: string | null;
  seller_name?: string | null;
  item_type: string;
  title: string;
  brand: string;
  mpn?: string;
  hsn_code?: string;
  gst_rate?: string | number;
  is_tax_verified?: boolean;
  unit_price: string | number;
  quantity: number;
  taxable_amount: string | number;
  cgst_amount: string | number;
  sgst_amount: string | number;
  igst_amount: string | number;
  tax_amount: string | number;
  total_amount: string | number;
  is_reviewed?: boolean;
  review?: PlatformProductReview | null;
}

export interface PlatformTrackingEvent {
  id: string;
  status: string;
  status_display?: string;
  location?: string;
  description: string;
  event_timestamp: string;
  external_checkpoint_id?: string;
  created_at: string;
}

export interface PlatformShipmentItem {
  id: string;
  order_item: string;
  order_item_id: string;
  listing_title: string;
  listing_brand: string;
  listing_mpn: string;
  quantity: number;
  created_at: string;
}

export interface PlatformShipment {
  id: string;
  shipment_number: string;
  order: string;
  order_number: string;
  seller_id: string;
  seller_name: string;
  organisation_name?: string | null;
  carrier: string;
  carrier_display?: string;
  carrier_name?: string;
  tracking_number: string;
  tracking_url?: string;
  status: "CREATED" | "DISPATCHED" | "IN_TRANSIT" | "OUT_FOR_DELIVERY" | "DELIVERED" | "FAILED_DELIVERY" | "RETURNED" | "CANCELLED";
  status_display?: string;
  dispatched_at?: string | null;
  delivered_at?: string | null;
  estimated_delivery_at?: string | null;
  delivery_notes?: string;
  items: PlatformShipmentItem[];
  tracking_events: PlatformTrackingEvent[];
  created_at: string;
  updated_at: string;
}

export interface CarrierOption {
  code: string;
  name: string;
}

export interface AvailableCarriersResponse {
  country: string;
  count: number;
  carriers: CarrierOption[];
}

export interface CreateShipmentPayload {
  carrier: string;
  carrier_name?: string;
  tracking_number?: string;
  tracking_url?: string;
  estimated_delivery_at?: string | null;
  delivery_notes?: string;
  dispatch_immediately?: boolean;
  items: Array<{
    order_item_id: string;
    quantity: number;
  }>;
}

export interface UpdateShipmentStatusPayload {
  status: string;
  location?: string;
  description?: string;
  carrier_reference?: string;
}

export interface CreateTrackingEventPayload {
  status?: string;
  description: string;
  location?: string;
  event_timestamp?: string;
  external_checkpoint_id?: string;
}

export interface PlatformOrder {
  id: string;
  order_number: string;
  idempotency_key?: string | null;
  buyer_email: string;
  buyer_name: string;
  status: string;
  payment_method: "ONLINE" | "COD";
  payment_status: "PENDING" | "AUTHORIZED" | "PAID" | "FAILED" | "CANCELLED" | "EXPIRED" | "REFUNDED";
  payment_reference?: string | null;
  paid_at?: string | null;
  cod_collection_status: "NOT_APPLICABLE" | "PENDING" | "AWAITING_COLLECTION" | "COLLECTED" | "FAILED_COLLECTION" | "CANCELLED";
  cod_collected_at?: string | null;
  cod_collected_by?: string | null;
  cod_collection_notes?: string;
  currency: string;
  place_of_supply: string;
  seller_state: string;
  shipping_name: string;
  shipping_phone: string;
  shipping_address_line1: string;
  shipping_address_line2?: string;
  shipping_city: string;
  shipping_state: string;
  shipping_postal_code: string;
  shipping_country: string;
  subtotal_taxable_amount: string | number;
  cgst_amount: string | number;
  sgst_amount: string | number;
  igst_amount: string | number;
  total_tax_amount: string | number;
  total_amount: string | number;
  items: PlatformOrderItem[];
  shipments?: PlatformShipment[];
  return_requests?: PlatformReturnRequest[];
  refunds?: PlatformRefund[];
  disputes?: PlatformDispute[];
  created_at: string;
  updated_at?: string;
}

export interface SellerOrder {
  id: string;
  order_number: string;
  buyer_email: string;
  buyer_name: string;
  status: string;
  payment_method: "ONLINE" | "COD";
  payment_status: "PENDING" | "AUTHORIZED" | "PAID" | "FAILED" | "CANCELLED" | "EXPIRED" | "REFUNDED";
  payment_reference?: string | null;
  paid_at?: string | null;
  cod_collection_status: "NOT_APPLICABLE" | "PENDING" | "AWAITING_COLLECTION" | "COLLECTED" | "FAILED_COLLECTION" | "CANCELLED";
  currency: string;
  place_of_supply: string;
  seller_state: string;
  shipping_name: string;
  shipping_phone: string;
  shipping_address_line1: string;
  shipping_address_line2?: string;
  shipping_city: string;
  shipping_state: string;
  shipping_postal_code: string;
  shipping_country: string;
  seller_subtotal_taxable_amount: string | number;
  seller_cgst_amount: string | number;
  seller_sgst_amount: string | number;
  seller_igst_amount: string | number;
  seller_total_tax_amount: string | number;
  seller_total_amount: string | number;
  seller_item_count: number;
  items: PlatformOrderItem[];
  shipments?: PlatformShipment[];
  return_requests?: PlatformReturnRequest[];
  refunds?: PlatformRefund[];
  disputes?: PlatformDispute[];
  created_at: string;
  updated_at?: string;
}

export interface PaymentMethodOption {
  code: "ONLINE" | "COD";
  provider: "RAZORPAY" | "STRIPE" | "COD";
  name: string;
  currency: string;
  is_available: boolean;
  reason?: string | null;
  description: string;
}

export interface AvailablePaymentMethodsResponse {
  status: string;
  country: string;
  currency: string;
  amount: string;
  payment_methods: PaymentMethodOption[];
}

export interface PaymentSessionResponse {
  provider: "RAZORPAY" | "STRIPE" | "COD";
  payment_method: "ONLINE" | "COD";
  amount: string;
  currency: string;
  provider_order_id?: string;
  key_id?: string;
  publishable_key?: string;
  client_secret?: string;
  payment_status?: string;
  cod_collection_status?: string;
  message?: string;
}

export interface PaymentVerifyPayload {
  razorpay_payment_id?: string;
  razorpay_order_id?: string;
  razorpay_signature?: string;
  payment_intent_id?: string;
  stripe_payment_intent_id?: string;
  client_secret?: string;
}

export interface PaymentVerifyResponse {
  status: "success" | "failed";
  message?: string;
  error?: string;
  payment_reference?: string;
  payment_status: string;
  order?: PlatformOrder;
  extra?: Record<string, unknown>;
}

export interface CODCollectionUpdatePayload {
  cod_collection_status: "AWAITING_COLLECTION" | "COLLECTED" | "FAILED_COLLECTION" | "CANCELLED";
  notes?: string;
}

export interface OrderPaymentDetailResponse {
  order_number: string;
  currency: string;
  total_amount: string;
  payment_method: "ONLINE" | "COD";
  payment_status: string;
  payment_reference?: string | null;
  paid_at?: string | null;
  cod_collection_status: string;
  cod_collected_at?: string | null;
  cod_collected_by?: string | null;
  cod_collection_notes?: string;
  transactions: Array<{
    id: string;
    transaction_type: string;
    provider: string;
    amount: string;
    currency: string;
    status: string;
    provider_transaction_id?: string;
    provider_order_id?: string;
    error_message?: string;
    created_at: string;
  }>;
}

export interface MarketplacePartListing {
  id: string;
  seller?: string;
  seller_id?: string;
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
  catalogue_part?: string | null;
  catalogue_part_name?: string | null;
  description?: string;
  price: string | number;
  compare_at_price?: string | number | null;
  price_flags?: {
    flag: string;
    median?: string | number | null;
    comparable_count?: number;
    deviation?: string | number | null;
  };
  currency: string;
  stock_quantity: number;
  low_stock_threshold?: number;
  availability?: "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK";
  condition: string;

  // Tax & Indian GST Fields
  hsn_code?: string;
  gst_rate?: string | number;
  is_tax_verified?: boolean;
  price_before_gst?: string | number;
  gst_amount?: string | number;
  total_price?: string | number;
  tax_breakdown?: TaxBreakdown;

  // Ratings & Reputation
  rating?: number;
  review_count?: number;
  seller_rating?: number;

  primary_image_url?: string;
  images?: string[];
  compatible_variants?: VehicleVariant[];
  compatibility_notes?: string;
  fitment?: BuyerPartFitment;
  fitment_verification?: FitmentVerificationItem[];
  fitment_summary?: FitmentSummary;
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

export interface PartBrowseCategoryFacet {
  id: string;
  name: string;
  slug: string;
  count: number;
}

export interface PartBrowseBrandFacet {
  brand: string;
  count: number;
}

export interface PartBrowseConditionFacet {
  condition: string;
  count: number;
}

export interface PartBrowseFacets {
  brands: PartBrowseBrandFacet[] | Record<string, number>;
  categories: PartBrowseCategoryFacet[];
  conditions: PartBrowseConditionFacet[] | Record<string, number>;
}

export interface PaginatedPartListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: MarketplacePartListing[];
  facets?: PartBrowseFacets;
}

export interface BrowsePartsParams {
  search?: string;
  category_id?: string;
  brand?: string;
  mpn?: string;
  condition?: string;
  in_stock?: boolean | string;
  price_max?: number | string;
  sort?: "newest" | "price_asc" | "price_desc" | "relevance" | string;
  fits_vehicle?: string;
  fits_only?: boolean | string;
  include_facets?: boolean | string;
  page?: number | string;
  page_size?: number | string;
  [key: string]: string | number | boolean | undefined;
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
  catalogue_part?: string | null;
  description?: string;
  price: number | string;
  compare_at_price?: number | string | null;
  currency?: string;
  stock_quantity?: number;
  low_stock_threshold?: number;
  condition?: string;
  hsn_code?: string;
  gst_rate?: number | string;
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

export interface PriceChange {
  id: string;
  listing: string;
  old_price: string | number;
  new_price: string | number;
  old_compare_at_price?: string | number | null;
  new_compare_at_price?: string | number | null;
  actor?: string | null;
  actor_name?: string | null;
  note?: string;
  created_at: string;
}

export interface CataloguePartOffer {
  id: string;
  price: string | number;
  compare_at_price?: string | number | null;
  currency: string;
  condition: string;
  stock_quantity: number;
  low_stock_threshold?: number;
  availability: "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK";
  seller_name?: string;
  organisation_name?: string | null;
  primary_image_url?: string;
  hsn_code?: string;
  gst_rate?: string | number;
  is_tax_verified?: boolean;
  price_before_gst?: string | number;
  gst_amount?: string | number;
  total_price?: string | number;
  tax_breakdown?: TaxBreakdown;
  created_at: string;
}

export interface UploadedImageResponse {
  id: string;
  url: string;
  absolute_url?: string;
  relative_url?: string;
  filename: string;
  size: number;
  content_type: string;
}

export interface SellerPublicInfo {
  name: string;
  seller_type: "DEALERSHIP" | "INDIVIDUAL_SELLER";
  is_verified: boolean;
  location_city: string;
  phone: string | null;
  has_phone: boolean;
  whatsapp_url: string | null;
  can_enquire: boolean;
}

export type VehicleEnquiryStatus = "NEW" | "RESPONDED" | "CLOSED";

export interface VehicleEnquiry {
  id: string;
  listing: string;
  listing_details?: {
    id: string;
    title: string;
    make_name?: string;
    model_name?: string;
    year?: number;
    price: string | number;
    currency: string;
    primary_image_url?: string;
    location_city?: string;
    status?: string;
  };
  buyer: string;
  buyer_name?: string;
  buyer_email?: string;
  buyer_phone?: string;
  seller: string;
  seller_name?: string;
  organisation?: string | null;
  organisation_name?: string | null;
  message: string;
  status: VehicleEnquiryStatus;
  seller_notes?: string;
  seller_reply?: string;
  replied_at?: string | null;
  responded_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateVehicleEnquiryPayload {
  message: string;
  buyer_phone?: string;
}

export interface UpdateVehicleEnquiryPayload {
  status?: VehicleEnquiryStatus;
  seller_notes?: string;
  seller_reply?: string;
}

// ==========================================
// Notifications Type Definitions
// ==========================================

export interface PlatformNotification {
  id: string;
  event_type: string;
  title: string;
  message: string;
  link: string;
  resource_type: string;
  resource_id: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface PaginatedNotificationsResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: PlatformNotification[];
}

// ==========================================
// Phase 5 Task 3: Returns, Refunds & Disputes
// ==========================================

export type ReturnRequestType = "CANCELLATION" | "RETURN";
export type ReturnRequestStatus = "PENDING" | "APPROVED" | "REJECTED" | "COMPLETED" | "CANCELLED";
export type ReturnReason =
  | "DEFECTIVE_ITEM"
  | "INCORRECT_ITEM"
  | "NOT_AS_DESCRIBED"
  | "ORDERED_BY_MISTAKE"
  | "DELIVERY_DELAY"
  | "BUYER_CANCEL"
  | "OTHER";

export interface PlatformReturnRequest {
  id: string;
  request_number: string;
  order?: string;
  order_id?: string;
  order_number: string;
  order_item?: string | null;
  order_item_id?: string | null;
  item_title?: string | null;
  item_brand?: string | null;
  buyer_id: string;
  buyer_name?: string | null;
  buyer_email?: string | null;
  seller_id: string;
  seller_name?: string | null;
  seller_email?: string | null;
  request_type: ReturnRequestType;
  request_type_display?: string;
  status: ReturnRequestStatus;
  status_display?: string;
  reason: ReturnReason;
  reason_display?: string;
  reason_category?: string;
  reason_category_display?: string;
  buyer_reason?: string;
  requested_quantity: number;
  refund_amount?: string | number;
  return_tracking_number?: string;
  order_currency?: string;
  items?: Array<{
    id?: string;
    title: string;
    brand: string;
    mpn?: string;
    quantity: number;
    unit_price: string | number;
    total_amount: string | number;
  }>;
  description: string;
  evidence_urls: string[];
  seller_notes?: string;
  rejection_reason?: string;
  reviewed_by_email?: string | null;
  reviewed_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type RefundStatus = "PENDING" | "PROCESSING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type RefundMethod = "ORIGINAL_PAYMENT" | "BANK_TRANSFER" | "MANUAL_PAYOUT";

export interface PlatformRefund {
  id: string;
  refund_number: string;
  order?: string;
  order_id?: string;
  order_number: string;
  return_request?: string | null;
  return_request_id?: string | null;
  return_request_number?: string | null;
  dispute?: string | null;
  dispute_id?: string | null;
  dispute_number?: string | null;
  amount: string | number;
  currency: string;
  refund_method?: RefundMethod;
  refund_method_display?: string;
  status: RefundStatus;
  status_display?: string;
  reason: string;
  reason_category?: string;
  gateway_provider?: string;
  gateway_refund_id?: string;
  gateway_reference?: string;
  gateway_response?: Record<string, unknown>;
  failure_reason?: string;
  notes?: string;
  created_by_email?: string | null;
  approved_by_email?: string | null;
  approved_at?: string | null;
  processed_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface OrderRefundSummary {
  order_number: string;
  currency: string;
  total_amount: string | number;
  payment_method: "ONLINE" | "COD";
  payment_status: string;
  cod_collection_status: string;
  is_cod: boolean;
  is_cod_collected: boolean;
  paid_amount: string | number;
  active_refunded_amount: string | number;
  available_refundable_balance: string | number;
  can_refund: boolean;
  reason_ineligible?: string | null;
  refunds: PlatformRefund[];
}

export type DisputeCategory =
  | "ITEM_NOT_RECEIVED"
  | "SIGNIFICANTLY_NOT_AS_DESCRIBED"
  | "DAMAGED_OR_DEFECTIVE"
  | "UNAUTHORIZED_TRANSACTION"
  | "REFUND_NOT_PROCESSED"
  | "CANCELLATION_ISSUE"
  | "OTHER";

export type DisputeStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED" | "REJECTED" | "ESCALATED";
export type DisputePriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type DisputeResolution = "BUYER_REFUND" | "REPLACEMENT" | "SELLER_UPHELD" | "MUTUAL_AGREEMENT" | "DISMISSED";

export interface PlatformDisputeEvent {
  id: string;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_email?: string | null;
  actor_role?: string | null;
  event_type: "OPENED" | "STATUS_CHANGED" | "MESSAGE" | "EVIDENCE_UPLOADED" | "RESOLVED" | "ESCALATED";
  message: string;
  attachments: string[];
  created_at: string;
}

export interface PlatformDispute {
  id: string;
  dispute_number: string;
  order?: string;
  order_id?: string;
  order_number: string;
  buyer_id: string;
  buyer_name?: string | null;
  buyer_email?: string | null;
  seller_id: string;
  seller_name?: string | null;
  seller_email?: string | null;
  category: DisputeCategory;
  category_display?: string;
  status: DisputeStatus;
  status_display?: string;
  priority: DisputePriority;
  description: string;
  evidence_urls: string[];
  resolution?: DisputeResolution | null;
  resolution_summary?: string;
  resolution_notes?: string;
  resolved_at?: string | null;
  resolved_by_email?: string | null;
  events: PlatformDisputeEvent[];
  created_at: string;
  updated_at: string;
}

export interface ItemEligibilityInfo {
  eligible: boolean;
  reason?: string;
  estimated_refund: string;
}

export interface OrderItemReturnEligibility {
  order_item_id: string;
  title: string;
  quantity: number;
  total_amount: string;
  cancellation: ItemEligibilityInfo;
  return: ItemEligibilityInfo;
}

export interface OrderReturnEligibilityResponse {
  order_number: string;
  currency: string;
  order_total: string;
  order_status: string;
  payment_status: string;
  order_cancellation: ItemEligibilityInfo;
  order_return: ItemEligibilityInfo;
  items: OrderItemReturnEligibility[];
}

export interface CreateReturnRequestPayload {
  order_item_id?: string;
  request_type: ReturnRequestType;
  reason: ReturnReason;
  requested_quantity?: number;
  description: string;
  evidence_urls?: string[];
}

export interface ReviewReturnRequestPayload {
  action: "APPROVE" | "REJECT";
  seller_notes?: string;
  rejection_reason?: string;
}

export interface CreateDisputePayload {
  category: DisputeCategory;
  description: string;
  evidence_urls?: string[];
  priority?: DisputePriority;
}

export interface CreateDisputeMessagePayload {
  message: string;
  attachments?: string[];
}

export interface CreateAdminRefundPayload {
  amount: string | number;
  reason: string;
  return_request_id?: string;
  dispute_id?: string;
  refund_method?: RefundMethod;
  notes?: string;
  auto_process?: boolean;
}

export interface UpdateDisputeStatusPayload {
  status: DisputeStatus;
  resolution?: DisputeResolution;
  resolution_notes?: string;
}

// ==========================================
// Review, Rating & Reputation Types (Task 4)
// ==========================================

export type ReviewStatus = "PENDING" | "APPROVED" | "FLAGGED" | "REJECTED";
export type ReviewReportReason = "SPAM" | "ABUSIVE" | "IRRELEVANT" | "FAKE_PURCHASE" | "CONFLICT_OF_INTEREST" | "OTHER";
export type ReviewReportStatus = "PENDING" | "RESOLVED" | "DISMISSED";
export type ReviewReportAction = "NO_ACTION" | "REVIEW_HIDDEN" | "REVIEW_DELETED" | "DISMISSED";

export interface PlatformProductReview {
  id: string;
  order: string;
  order_id?: string;
  order_number: string;
  order_item: string;
  order_item_id: string;
  listing: string;
  listing_id: string;
  listing_name: string;
  part_name?: string;
  buyer_id: string;
  buyer_name: string;
  user_full_name?: string;
  user_email?: string;
  seller_id: string;
  seller_name: string;
  organisation_id?: string | null;
  organisation_name?: string | null;
  rating: number;
  title: string;
  headline?: string;
  comment: string;
  status: ReviewStatus;
  is_verified_purchase: boolean;
  seller_reply?: string;
  seller_reply_at?: string | null;
  has_seller_reply: boolean;
  seller_replied_by_name?: string | null;
  helpful_votes: number;
  helpful_count?: number;
  has_voted_helpful?: boolean;
  moderation_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface PlatformSellerReview {
  id: string;
  order: string;
  order_number: string;
  buyer_id: string;
  buyer_name: string;
  seller_id: string;
  seller_name: string;
  organisation_id?: string | null;
  organisation_name?: string | null;
  rating: number;
  communication_rating?: number | null;
  delivery_rating?: number | null;
  item_description_rating?: number | null;
  comment: string;
  status: ReviewStatus;
  is_verified_purchase: boolean;
  seller_reply?: string;
  seller_reply_at?: string | null;
  has_seller_reply: boolean;
  seller_replied_by_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformReviewReport {
  id: string;
  product_review?: string | null;
  product_review_detail?: PlatformProductReview | null;
  review_detail?: PlatformProductReview | null;
  seller_review?: string | null;
  seller_review_detail?: PlatformSellerReview | null;
  review_type: "PRODUCT" | "SELLER";
  target_review_title?: string;
  target_review_comment?: string;
  target_review_rating?: number;
  target_review_status?: string;
  reporter_id: string;
  reporter_name: string;
  reporter_email: string;
  reason: ReviewReportReason;
  reason_display?: string;
  details: string;
  status: ReviewReportStatus;
  action_taken?: ReviewReportAction;
  admin_notes?: string;
  resolved_at?: string | null;
  resolved_by_name?: string | null;
  created_at: string;
}

export interface ProductRatingSummary {
  average_rating: number;
  review_count: number;
  distribution: {
    "1": number;
    "2": number;
    "3": number;
    "4": number;
    "5": number;
  };
  recommendation_percentage: number;
}

export interface SellerReputationSummary {
  seller_id: string;
  seller_name: string;
  average_rating: number;
  positive_percentage: number;
  positive_feedback_rate?: number;
  response_rate: number;
  total_reviews_count: number;
  review_count?: number;
  seller_reviews_count: number;
  product_reviews_count: number;
  communication_avg: number;
  delivery_avg: number;
  item_description_avg: number;
  rating_distribution: {
    "1": number;
    "2": number;
    "3": number;
    "4": number;
    "5": number;
  };
  rating_breakdown?: {
    "1": number;
    "2": number;
    "3": number;
    "4": number;
    "5": number;
  };
}

export interface OrderReviewItemEligibility {
  order_item_id: string;
  listing_id: string;
  listing_title: string;
  listing_brand: string;
  seller_id: string;
  seller_name: string;
  eligible: boolean;
  reason?: string;
  is_reviewed: boolean;
  review_id?: string | null;
  rating?: number | null;
}

export interface OrderReviewEligibilityResponse {
  order_id: string;
  order_number: string;
  order_status: string;
  eligible: boolean;
  reason?: string;
  items: OrderReviewItemEligibility[];
}

export interface CreateProductReviewPayload {
  order_item_id: string;
  rating: number;
  title?: string;
  comment: string;
  seller_rating?: number;
  seller_comment?: string;
}

export interface CreateSellerRatingPayload {
  order_id: string;
  seller_id: string;
  rating: number;
  communication_rating?: number;
  delivery_rating?: number;
  item_description_rating?: number;
  comment?: string;
}

