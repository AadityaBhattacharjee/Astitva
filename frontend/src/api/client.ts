/**
 * Astitva API client — all backend calls go through here.
 * JWT token is read from localStorage and attached as Authorization header.
 */

const BASE_URL = "/api/v1";
const TOKEN_KEY = "astitva.token";

// ---------------------------------------------------------------------------
// Token helpers
// ---------------------------------------------------------------------------

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  requireAuth = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (requireAuth) {
    const token = getToken();
    if (!token) {
      throw new ApiError(401, "Not authenticated");
    }
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearToken();
    throw new ApiError(401, "Unauthorized — please log in again.");
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const authApi = {
  register: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>(
      "/auth/register",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
      false,
    ),

  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
      false,
    ),
};

// ---------------------------------------------------------------------------
// Users / Profile
// ---------------------------------------------------------------------------

export const userApi = {
  getMe: () =>
    request<{
      id: number;
      email: string;
      role: string;
      is_active: boolean;
    }>("/users/me"),

  getProfile: () =>
    request<{
      id: number;
      user_id: number;
      full_name: string | null;
      state: string | null;
      language: string | null;
      onboarding_data: Record<string, unknown>;
      onboarding_completed_at: string | null;
    }>("/profile/me"),

  upsertProfile: (payload: {
    full_name?: string | null;
    state?: string | null;
    language?: string | null;
    onboarding_data: Record<string, unknown>;
    onboarding_completed_at?: string | null;
  }) =>
    request<{
      id: number;
      user_id: number;
      full_name: string | null;
      state: string | null;
      language: string | null;
      onboarding_data: Record<string, unknown>;
      onboarding_completed_at: string | null;
    }>("/profile/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};

export const roadmapApi = {
  getMine: () =>
    request<{
      roadmap: {
        id: number;
        user_id: number;
        title: string;
        summary: string | null;
        status: string;
        tasks: Array<{
          id: number;
          roadmap_id: number;
          title: string;
          description: string | null;
          sequence: number;
          status: string;
          priority: string;
        }>;
      };
      progress: {
        id: number;
        roadmap_id: number;
        status: string;
        completed_milestones: number;
        missed_milestones: number;
        overdue_tasks: number;
        engagement_history: string[];
      };
      created: boolean;
    }>("/roadmaps/me"),

  generate: (force_refresh = false) =>
    request<{
      roadmap: {
        id: number;
        user_id: number;
        title: string;
        summary: string | null;
        status: string;
        tasks: Array<{
          id: number;
          roadmap_id: number;
          title: string;
          description: string | null;
          sequence: number;
          status: string;
          priority: string;
        }>;
      };
      progress: {
        id: number;
        roadmap_id: number;
        status: string;
        completed_milestones: number;
        missed_milestones: number;
        overdue_tasks: number;
        engagement_history: string[];
      };
      created: boolean;
    }>("/roadmaps/generate", {
      method: "POST",
      body: JSON.stringify({ force_refresh }),
    }),

  updateTask: (taskId: number, statusValue: string) =>
    request<{
      roadmap: {
        id: number;
        user_id: number;
        title: string;
        summary: string | null;
        status: string;
        tasks: Array<{
          id: number;
          roadmap_id: number;
          title: string;
          description: string | null;
          sequence: number;
          status: string;
          priority: string;
        }>;
      };
      progress: {
        id: number;
        roadmap_id: number;
        status: string;
        completed_milestones: number;
        missed_milestones: number;
        overdue_tasks: number;
        engagement_history: string[];
      };
      created: boolean;
    }>(`/roadmaps/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: statusValue }),
    }),
};

export const progressApi = {
  getMine: () =>
    request<{
      id: number;
      roadmap_id: number;
      status: string;
      completed_milestones: number;
      missed_milestones: number;
      overdue_tasks: number;
      engagement_history: string[];
    }>("/progress/me"),
};

// ---------------------------------------------------------------------------
// Schemes
// ---------------------------------------------------------------------------

export const schemesApi = {
  list: (params?: { state?: string; category?: string }) => {
    const qs = params
      ? "?" + new URLSearchParams(params as Record<string, string>).toString()
      : "";
    return request<{
      scheme_id: string;
      scheme_name: string;
      description: string | null;
      category: string | null;
      state: string | null;
      benefits: string[];
      active_status: boolean;
    }[]>(`/schemes/${qs}`);
  },
};

// ---------------------------------------------------------------------------
// Agents (all 12 — all JWT-protected)
// ---------------------------------------------------------------------------

export const agentApi = {
  government: (payload: {
    query: string;
    state?: string;
    category?: string;
    target_group?: string;
    age?: number;
    income?: number;
    vector_limit?: number;
  }) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      recommended_schemes: Record<string, unknown>[];
      additional_context: string;
      evidence_summary: Record<string, number>;
      sources: string[];
    }>("/agents/government", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  supervisor: (query: string) =>
    request<{
      agent_name: string;
      status: string;
      summary: string;
      routed_to: string | null;
      intent: string;
      method: string;
    }>("/agents/supervisor", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  document: (query: string, vector_limit = 5) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      guidance: Record<string, unknown>[];
      required_documents: string[];
      evidence_summary: Record<string, unknown>;
      sources: string[];
    }>("/agents/document", {
      method: "POST",
      body: JSON.stringify({ query, vector_limit }),
    }),

  case_worker: (query: string) =>
    request<{
      agent_name: string;
      status: string;
      case_summary: string;
      priority_actions: Record<string, unknown>[];
      document_gaps: string[];
      roadmap_status: string;
      risk_flags: string[];
      case_meta: Record<string, unknown>;
    }>("/agents/case_worker", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  employment: (payload: {
    query: string;
    state?: string;
    target_group?: string;
    age?: number;
    vector_limit?: number;
  }) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      job_options: Record<string, unknown>[];
      skills_guidance: string[];
      next_actions: string[];
      evidence_summary: Record<string, unknown>;
      sources: string[];
    }>("/agents/employment", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  finance: (payload: {
    query: string;
    state?: string;
    target_group?: string;
    age?: number;
    income?: number;
    vector_limit?: number;
  }) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      financial_options: Record<string, unknown>[];
      budgeting_tips: string[];
      next_actions: string[];
      disclaimer: string;
      evidence_summary: Record<string, unknown>;
      sources: string[];
    }>("/agents/finance", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  healthcare: (payload: {
    query: string;
    state?: string;
    target_group?: string;
    age?: number;
    income?: number;
    vector_limit?: number;
  }) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      healthcare_schemes: Record<string, unknown>[];
      next_actions: string[];
      medical_disclaimer: string;
      evidence_summary: Record<string, unknown>;
      sources: string[];
    }>("/agents/healthcare", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  legal: (payload: {
    query: string;
    state?: string;
    target_group?: string;
    vector_limit?: number;
  }) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      legal_information: Record<string, unknown>[];
      suggested_resources: string[];
      next_actions: string[];
      legal_disclaimer: string;
      evidence_summary: Record<string, unknown>;
      sources: string[];
    }>("/agents/legal", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  mentor_matching: (query: string) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      ideal_mentor_profile: Record<string, unknown>;
      recommended_channels: string[];
      next_actions: string[];
      disclaimer: string;
      no_mentor_db: boolean;
      profile_used: Record<string, unknown>;
    }>("/agents/mentor_matching", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  planning: (query: string) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      existing_plan_summary: Record<string, unknown>;
      recommended_next_actions: Record<string, unknown>[];
      gaps_identified: string[];
      disclaimer: string;
      context_meta: Record<string, unknown>;
    }>("/agents/planning", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  progress: (query: string) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      progress_summary: Record<string, unknown>;
      achievements: string[];
      pending_actions: string[];
      next_recommended_step: string;
      context_meta: Record<string, unknown>;
    }>("/agents/progress", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  risk: (query: string) =>
    request<{
      agent_name: string;
      status: string;
      answer: string;
      risk_level: string;
      risk_score: number;
      risk_flags: string[];
      risk_interpretation: string;
      observed_risk_factors: string[];
      inferred_risk_factors: string[];
      recommended_interventions: string[];
      risk_features: Record<string, unknown>;
      context_meta: Record<string, unknown>;
    }>("/agents/risk", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  list: () =>
    request<{ implemented: string[]; placeholder: string[] }>("/agents/", {}, false),
};

export { ApiError };
