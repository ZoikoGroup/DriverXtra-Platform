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
        tokenStorage.clearTokens();
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
    } catch {
      tokenStorage.clearTokens();
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
      if (typeof dataObj.message === "string") {
        message = dataObj.message;
      } else if (typeof dataObj.detail === "string") {
        message = dataObj.detail;
      }
      details = (dataObj.details || data) as Record<string, string[] | string> | string[] | string;
      // Extract field errors if present
      if (dataObj.details && typeof dataObj.details === "object") {
        const detailsObj = dataObj.details as Record<string, unknown>;
        const firstKey = Object.keys(detailsObj)[0];
        if (firstKey && Array.isArray(detailsObj[firstKey]) && detailsObj[firstKey][0]) {
          message = `${firstKey}: ${detailsObj[firstKey][0]}`;
        }
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
  tokens: {
    access: string;
    refresh: string;
  };
  user: BackendUserProfile;
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

export const api = {
  auth: {
    async login(email: string, password: string): Promise<LoginResponse> {
      const data = await apiRequest<LoginResponse>("/auth/login/", {
        method: "POST",
        requiresAuth: false,
        body: JSON.stringify({ email, password }),
      });
      if (!data?.tokens?.access || !data?.tokens?.refresh) {
        throw new ApiError("Authentication failed: both access and refresh tokens are required.", 500);
      }
      tokenStorage.setTokens(data.tokens.access, data.tokens.refresh);
      return data;
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
};
