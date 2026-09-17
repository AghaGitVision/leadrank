export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Mode = "sell" | "buy";

export interface Profile {
  id: string;
  name: string;
  mode: Mode;
  is_builtin: boolean;
  weights: Record<string, number>;
  targeting: Record<string, unknown>;
}

export interface Run {
  id: string;
  profile_id: string;
  filename: string;
  row_count: number;
  status: string;
  progress: number;
  stats: {
    input_rows?: number;
    exact_merges?: number;
    fuzzy_merges?: number;
    suppressed?: number;
    bands?: Record<string, number>;
    quadrants?: Record<string, number>;
    scan_statuses?: Record<string, number>;
    scan_cache_hit_rate?: number;
    cache_backend?: string;
    alerts?: number;
    error?: string;
  };
}

export interface Lead {
  id: string;
  company_name: string;
  domain: string | null;
  country: string | null;
  city: string | null;
  industry: string | null;
  employee_count: number | null;
  revenue_estimate: number | null;
  owner_name: string | null;
  email: string | null;
  email_status: string;
  phone: string | null;
  linkedin_url: string | null;
  score: number;
  band: string;
  confidence: number;
  quadrant: string;
  narrative: string | null;
  review_state: string;
  enriched: boolean;
  scan_status: string;
}

export interface Signal {
  dimension: string;
  signal_key: string;
  label: string;
  normalized_value: number | null;
  weight: number;
  contribution: number;
  forgone: number;
  present: boolean;
  source: string;
}

export interface Explain {
  lead: Lead;
  dimension_scores: Record<string, number>;
  gained: Signal[];
  lost: Signal[];
  missing: Signal[];
  scan: Record<string, any>;
  provenance: Record<string, any>;
  merged_from: string[];
}

export interface WeightSchema {
  [mode: string]: {
    defaults: Record<string, number>;
    dimensions: { key: string; label: string; signals: { key: string; label: string }[] }[];
  };
}

export interface LearningProposal {
  dimension: string;
  current: number;
  proposed: number;
  accepted_mean: number;
  rejected_mean: number;
  separation: number;
  delta: number;
}

export interface SuppressionEntry {
  domain: string;
  reason: string;
  created_at: string;
}

export interface Alert {
  id: string;
  domain: string;
  lead_id: string | null;
  kind: string;
  detail: string;
  severity: string;
  created_at: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  profiles: () => request<Profile[]>("/api/v1/profiles"),
  weightSchema: () => request<WeightSchema>("/api/v1/profiles/schema"),
  createProfile: (body: Partial<Profile>) =>
    request<Profile>("/api/v1/profiles", { method: "POST", body: JSON.stringify(body) }),
  updateProfile: (id: string, body: Partial<Profile>) =>
    request<Profile>(`/api/v1/profiles/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  cloneProfile: (id: string) =>
    request<Profile>(`/api/v1/profiles/${id}/clone`, { method: "POST" }),

  preview: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/api/v1/runs/preview`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{
      mapping: Record<string, string>;
      unmapped: string[];
      missing_required: string[];
      samples: Record<string, string>[];
    }>;
  },

  createRun: async (file: File, profileId: string, mapping?: Record<string, string>) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("profile_id", profileId);
    if (mapping) fd.append("mapping", JSON.stringify(mapping));
    const res = await fetch(`${API_BASE}/api/v1/runs`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Run>;
  },

  run: (id: string) => request<Run>(`/api/v1/runs/${id}`),
  runs: () => request<Run[]>("/api/v1/runs"),

  leads: (runId: string, params: Record<string, string | number> = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v !== undefined).map(([k, v]) => [k, String(v)]),
    );
    return request<{ total: number; items: Lead[] }>(`/api/v1/runs/${runId}/leads?${qs}`);
  },

  explain: (leadId: string) => request<Explain>(`/api/v1/leads/${leadId}/explain`),

  review: (leadId: string, state: string) =>
    request<Lead>(`/api/v1/leads/${leadId}`, {
      method: "PATCH",
      body: JSON.stringify({ review_state: state }),
    }),

  enrich: (leadId: string) =>
    request<Lead>(`/api/v1/leads/${leadId}/enrich`, { method: "POST" }),

  rescore: (runId: string, body: { weights?: Record<string, number>; profile_id?: string }) =>
    request<Run>(`/api/v1/runs/${runId}/rescore`, { method: "POST", body: JSON.stringify(body) }),

  learning: (runId: string) =>
    request<{
      eligible: boolean;
      reason: string;
      sample_size: number;
      accepted: number;
      rejected: number;
      proposals: LearningProposal[];
    }>(`/api/v1/runs/${runId}/learning`),

  alerts: (runId?: string) =>
    request<Alert[]>(runId ? `/api/v1/alerts?run_id=${runId}` : "/api/v1/alerts"),

  rescan: (runId: string) =>
    request<{ rescanned: number; changes: number }>(`/api/v1/runs/${runId}/rescan`, {
      method: "POST",
    }),

  exportUrl: (runId: string, format: string, state: string) =>
    `${API_BASE}/api/v1/runs/${runId}/export?format=${format}&state=${state}`,

  health: () => request<{ status: string; env: string; scan_mode: string; cache_backend: string; cache_hit_rate: number }>("/health"),

  suppressionList: () => request<SuppressionEntry[]>("/api/v1/suppression"),
  addSuppression: (domain: string, reason: string) =>
    request<{ domain: string; suppressed: boolean }>(
      `/api/v1/suppression?${new URLSearchParams({ domain, reason })}`,
      { method: "POST" },
    ),
  removeSuppression: (domain: string) =>
    request<{ domain: string; suppressed: boolean }>(
      `/api/v1/suppression/${encodeURIComponent(domain)}`,
      { method: "DELETE" },
    ),
};

export const bandColor: Record<string, string> = {
  A: "text-band-a border-band-a/40 bg-band-a/10",
  B: "text-band-b border-band-b/40 bg-band-b/10",
  C: "text-band-c border-band-c/40 bg-band-c/10",
  D: "text-band-d border-band-d/40 bg-band-d/10",
};

export const quadrantLabel: Record<string, string> = {
  act: "Contact now",
  verify: "Enrich to verify",
  pass: "Suppress",
  recheck: "Rescan first",
};

export function money(v: number | null): string {
  if (!v) return "—";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)}k`;
  return `$${v}`;
}
