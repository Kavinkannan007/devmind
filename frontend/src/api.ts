import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const supabase = url && key ? createClient(url, key) : null;
export const setupHint =
  "Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env.local, then restart the frontend.";
export async function api<T>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  if (!supabase) throw new Error(setupHint);
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session)
    throw new Error("Sign in to access your workspace.");
  const root = (
    import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(root + path, {
      method: method || (body === undefined ? "GET" : "POST"),
      headers: {
        Authorization: "Bearer " + data.session.access_token,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(120000),
    });
  } catch {
    throw new Error(
      "The API could not be reached in time. Check your connection and backend URL.",
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : "The request failed (HTTP " + response.status + ").",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export type Source = { path: string; language: string; lines: number };
export type Citation = {
  path: string;
  start_line: number;
  end_line: number;
  sha: string;
  url: string;
  label?: string;
  text?: string;
  symbol?: string;
};
export type Job = {
  status: string;
  stage: string;
  done: number;
  total: number;
  error?: string;
};
export type RepoRow = {
  id: string;
  name: string;
  url: string;
  sha: string | null;
  status?: string;
  job?: Job;
};
export type Edge = {
  source: string;
  target: string;
  kind: string;
  line: number;
};
export type SymbolInfo = {
  path: string;
  name: string;
  kind: string;
  start_line: number;
  end_line: number;
};
export type Repo = RepoRow & {
  job: Job;
  metadata: {
    description?: string;
    default_branch?: string;
    stars?: number;
    forks?: number;
    truncated?: boolean;
    skipped_files?: { path: string; reason: string }[];
    updated_at?: string;
    languages?: Record<string, number>;
    discovered?: number;
    skipped?: Record<string, number>;
    frameworks?: string[];
  };
  files: Source[];
  edges: Edge[];
  symbols: SymbolInfo[];
};
export type Answer = {
  question?: string;
  answer: string;
  citations: Citation[];
};
export const errorText = (reason: unknown) =>
  reason instanceof Error
    ? reason.message
    : "The request failed. Please try again.";
