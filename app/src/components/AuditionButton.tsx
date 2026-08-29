export function AuditionButton({
  onStart,
  onReset,
  running,
  starting,
  canStart,
  finished,
}: {
  onStart: () => void;
  onReset: () => void;
  running: boolean;
  starting: boolean;
  canStart: boolean;
  finished: boolean;
}) {
  return (
    <div className="actions">
      <button
        type="button"
        className="btn btn--primary"
        onClick={onStart}
        disabled={!canStart || running || starting}
      >
        {starting ? "Starting…" : running ? "Audition in progress…" : "Start Audition"}
      </button>

      {(running || finished) && (
        <button type="button" className="btn btn--ghost" onClick={onReset}>
          {running ? "Cancel" : "New audition"}
        </button>
      )}
    </div>
  );
}
