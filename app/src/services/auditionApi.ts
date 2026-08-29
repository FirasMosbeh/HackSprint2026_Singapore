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
 * implementation behind it (agent/ + testing/, Daytona, whatever comes next)
 * can change completely without touching the UI.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE !== "false";

export interface ApiMode {
  demo: boolean;
  /** True once a real request has succeeded, false after a failure. */
  connected: boolean;
  reason?: string;
}

let liveConnected = false;
let liveReason: string | undefined;
/** Set when a live call fails and we transparently fall back to the mock. */
let fellBackToDemo = false;

export function getApiMode(): ApiMode {
  if (DEMO_MODE || fellBackToDemo) {
    return {
      demo: true,
      connected: true,
      reason: DEMO_MODE
        ? "Demo mode — results are simulated locally."
        : "Backend unavailable. Running in demo mode.",
    };
  }
  return { demo: false, connected: liveConnected, reason: liveReason };
}

export function isDemoMode(): boolean {
  return DEMO_MODE || fellBackToDemo;
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
  if (isDemoMode()) {
    return createMockAudition(req);
  }
  try {
    const audition = await request<Audition>("/auditions", {
      method: "POST",
      body: JSON.stringify(req),
    });
    liveConnected = true;
    liveReason = undefined;
    return audition;
  } catch (error) {
    // A missing backend must never dead-end the demo.
    fellBackToDemo = true;
    liveConnected = false;
    liveReason = error instanceof Error ? error.message : String(error);
    return createMockAudition(req);
  }
}

export async function getAuditionStatus(
  id: string,
): Promise<Pick<Audition, "id" | "status">> {
  if (isDemoMode()) {
    const audition = getMockAudition(id);
    if (!audition) throw new Error(`Unknown audition ${id}`);
    return { id: audition.id, status: audition.status };
  }
  return request<Pick<Audition, "id" | "status">>(`/auditions/${id}/status`);
}

export async function getAuditionResults(id: string): Promise<Audition> {
  if (isDemoMode()) {
    const audition = getMockAudition(id);
    if (!audition) throw new Error(`Unknown audition ${id}`);
    return audition;
  }
  try {
    const audition = await request<Audition>(`/auditions/${id}`);
    liveConnected = true;
    return audition;
  } catch (error) {
    liveConnected = false;
    liveReason = error instanceof Error ? error.message : String(error);
    throw error;
  }
}

export async function cancelAudition(id: string): Promise<void> {
  if (isDemoMode()) {
    cancelMockAudition(id);
    return;
  }
  await request<void>(`/auditions/${id}`, { method: "DELETE" });
}
