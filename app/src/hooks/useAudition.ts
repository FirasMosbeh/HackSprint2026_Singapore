import { useCallback, useEffect, useRef, useState } from "react";
import type { Audition, AuditionRequest } from "../types/audition";
import { isTerminal } from "../types/audition";
import {
  cancelAudition,
  getApiMode,
  getAuditionResults,
  startAudition,
} from "../services/auditionApi";

const POLL_INTERVAL_MS = 400;

export interface UseAudition {
  audition: Audition | null;
  isStarting: boolean;
  isRunning: boolean;
  error: string | null;
  mode: ReturnType<typeof getApiMode>;
  start: (request: AuditionRequest) => Promise<void>;
  reset: () => void;
}

/**
 * Owns the lifecycle of one audition: start it, poll it until it settles,
 * surface partial results the whole way through.
 *
 * Polling is deliberately dumb. If the backend later exposes a WebSocket or
 * SSE stream, only this hook changes.
 */
export function useAudition(): UseAudition {
  const [audition, setAudition] = useState<Audition | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState(getApiMode);

  const timer = useRef<number | null>(null);
  const consecutiveFailures = useRef(0);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback(
    async (id: string) => {
      try {
        const next = await getAuditionResults(id);
        consecutiveFailures.current = 0;
        setAudition(next);
        setMode(getApiMode());
        if (isTerminal(next.status)) stopPolling();
      } catch (err) {
        consecutiveFailures.current += 1;
        // Tolerate a couple of blips before giving up on the run.
        if (consecutiveFailures.current >= 5) {
          stopPolling();
          setError(
            err instanceof Error
              ? `Lost contact with the evaluation backend: ${err.message}`
              : "Lost contact with the evaluation backend.",
          );
          setMode(getApiMode());
        }
      }
    },
    [stopPolling],
  );

  const start = useCallback(
    async (request: AuditionRequest) => {
      stopPolling();
      setError(null);
      setIsStarting(true);
      consecutiveFailures.current = 0;
      try {
        const created = await startAudition(request);
        setAudition(created);
        setMode(getApiMode());
        if (!isTerminal(created.status)) {
          timer.current = window.setInterval(() => {
            void poll(created.id);
          }, POLL_INTERVAL_MS);
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? `Could not start the audition: ${err.message}`
            : "Could not start the audition.",
        );
      } finally {
        setIsStarting(false);
      }
    },
    [poll, stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    if (audition && !isTerminal(audition.status)) {
      void cancelAudition(audition.id).catch(() => undefined);
    }
    setAudition(null);
    setError(null);
  }, [audition, stopPolling]);

  return {
    audition,
    isStarting,
    isRunning: audition ? !isTerminal(audition.status) : false,
    error,
    mode,
    start,
    reset,
  };
}
