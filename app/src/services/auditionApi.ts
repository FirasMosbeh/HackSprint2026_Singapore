import type { Audition, AuditionRequest } from "../types/audition";
import {
  cancelMockAudition,
  createMockAudition,
  getMockAudition,
} from "./mockEngine";

/**
 * The only place in the app that knows a backend exists.
 *
 * Components and hooks talk to this module and nothing else, so the real
 * implementation behind it (agent/ + testing/) can change completely without
 * touching the UI.
 *
 * Mode is decided once, at startup, by probing the agent's health endpoint:
 *   VITE_DEMO_MODE=true   → always mock
 *   VITE_DEMO_MODE=false  → always live (errors surface instead of falling back)
 *   unset                 → live if the agent answers, mock if it does not
 */

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const DEMO_FLAG = import.meta.env.VITE_DEMO_MODE;
const FORCED_DEMO = DEMO_FLAG === "true";
const FORCED_LIVE = DEMO_FLAG === "false";

const HEALTH_TIMEOUT_MS = 2000;

export interface ApiMode {
  demo: boolean;
  connected: boolean;
  reason?: string;
}

let demo = FORCED_DEMO;
let connected = false;
let reason: string | undefined = FORCED_DEMO
  ? "Demo mode — results are simulated locally."
  : undefined;

/** Resolves once the startup probe has settled, so the UI never flickers. */
let probe: Promise<ApiMode> | null = null;

export function getApiMode(): ApiMode {
  return { demo, connected: demo ? true : connected, reason };
}

export function isDemoMode(): boolean {
  return demo;
}

/**
 * Probe the agent once. Safe to call repeatedly — the result is cached.
 */
export function detectMode(): Promise<ApiMode> {
  if (probe) return probe;

  if (FORCED_DEMO) {
    probe = Promise.resolve(getApiMode());
    return probe;
  }

  probe = (async () => {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
      const response = await fetch(`${API_BASE}/api/health`, {
        signal: controller.signal,
      });
      clearTimeout(timer);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

      demo = false;
      connected = true;
      reason = "Live — agent + testing sandboxes.";
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      if (FORCED_LIVE) {
        demo = false;
        connected = false;
        reason = `Agent unreachable: ${detail}`;
      } else {
        demo = true;
        connected = true;
        reason = "Agent unreachable. Running in demo mode.";
      }
    }
    return getApiMode();
  })();

  return probe;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function startAudition(req: AuditionRequest): Promise<Audition> {
  await detectMode();
  if (demo) return createMockAudition(req);

  try {
    const audition = await request<Audition>("/auditions", {
      method: "POST",
      body: JSON.stringify(req),
    });
    connected = true;
    reason = "Live — agent + testing sandboxes.";
    return audition;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    if (FORCED_LIVE) {
      connected = false;
      reason = `Agent unreachable: ${detail}`;
      throw error;
    }
    // A backend that dies mid-session must never dead-end the demo.
    demo = true;
    connected = true;
    reason = "Agent unreachable. Running in demo mode.";
    return createMockAudition(req);
  }
}

export async function getAuditionStatus(
  id: string,
): Promise<Pick<Audition, "id" | "status">> {
  if (demo) {
    const audition = getMockAudition(id);
    if (!audition) throw new Error(`Unknown audition ${id}`);
    return { id: audition.id, status: audition.status };
  }
  return request<Pick<Audition, "id" | "status">>(`/auditions/${id}/status`);
}

export async function getAuditionResults(id: string): Promise<Audition> {
  if (demo) {
    const audition = getMockAudition(id);
    if (!audition) throw new Error(`Unknown audition ${id}`);
    return audition;
  }
  try {
    const audition = await request<Audition>(`/auditions/${id}`);
    connected = true;
    return audition;
  } catch (error) {
    connected = false;
    reason = error instanceof Error ? error.message : String(error);
    throw error;
  }
}

export async function cancelAudition(id: string): Promise<void> {
  if (demo) {
    cancelMockAudition(id);
    return;
  }
  await request<void>(`/auditions/${id}`, { method: "DELETE" });
}
