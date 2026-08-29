import { useState } from "react";
import type { Candidate } from "../types/audition";

export function CandidateSelector({
  candidates,
  onChange,
  disabled,
}: {
  candidates: Candidate[];
  onChange: (candidates: Candidate[]) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const name = draft.trim();
    if (!name) return;
    if (candidates.some((c) => c.name.toLowerCase() === name.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...candidates, { name, package: name, ecosystem: "pypi" }]);
    setDraft("");
  };

  const remove = (name: string) =>
    onChange(candidates.filter((c) => c.name !== name));

  return (
    <section className="panel">
      <header className="panel__head">
        <h2 className="panel__title">Candidate libraries</h2>
        <span className="panel__hint">
          {candidates.length} {candidates.length === 1 ? "candidate" : "candidates"} — each
          one gets its own isolated environment.
        </span>
      </header>

      <div className="chips">
        {candidates.map((candidate) => (
          <span className="chip" key={candidate.name}>
            {candidate.name}
            <button
              type="button"
              className="chip__remove"
              aria-label={`Remove ${candidate.name}`}
              disabled={disabled}
              onClick={() => remove(candidate.name)}
            >
              ×
            </button>
          </span>
        ))}

        <input
          className="chip-input"
          value={draft}
          disabled={disabled}
          placeholder="add a library…"
          spellCheck={false}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
            if (event.key === "Backspace" && !draft && candidates.length) {
              remove(candidates[candidates.length - 1].name);
            }
          }}
        />
      </div>

      {candidates.length === 0 && (
        <p className="empty-hint">
          Add at least one library to audition.
        </p>
      )}
    </section>
  );
}
