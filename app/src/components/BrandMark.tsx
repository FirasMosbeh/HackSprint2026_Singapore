/** Sentrya's mark: a sentry ring watching a fixed point. */
export function BrandMark({ size = 44 }: { size?: number }) {
  return (
    <svg
      className="mark"
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="sentrya-mark" x1="8" y1="4" x2="40" y2="44">
          <stop offset="0%" stopColor="#8aa6ff" />
          <stop offset="100%" stopColor="#3fb950" />
        </linearGradient>
      </defs>
      <rect
        x="1.5"
        y="1.5"
        width="45"
        height="45"
        rx="12"
        stroke="url(#sentrya-mark)"
        strokeOpacity="0.45"
        strokeWidth="1.5"
      />
      <path
        d="M24 9c8.3 0 15 6.7 15 15s-6.7 15-15 15"
        stroke="url(#sentrya-mark)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M24 15.5a8.5 8.5 0 1 0 0 17"
        stroke="url(#sentrya-mark)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeOpacity="0.7"
      />
      <circle cx="24" cy="24" r="3.2" fill="url(#sentrya-mark)" />
    </svg>
  );
}
