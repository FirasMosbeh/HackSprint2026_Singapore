export function RequirementInput({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <section className="panel">
      <header className="panel__head">
        <h2 className="panel__title">What do you need?</h2>
        <span className="panel__hint">
          Described in plain language — this becomes the test suite every candidate runs.
        </span>
      </header>
      <textarea
        className="requirement"
        value={value}
        rows={3}
        disabled={disabled}
        spellCheck={false}
        placeholder='e.g. I need a Python library that can parse human-written dates such as "next Tuesday"…'
        onChange={(event) => onChange(event.target.value)}
      />
    </section>
  );
}
