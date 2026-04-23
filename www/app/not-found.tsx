import Link from "next/link";

function LostOctopus() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 220"
      width={160}
      height={176}
      aria-hidden="true"
      style={{ animation: "bob 3s ease-in-out infinite" }}
    >
      <g transform="rotate(-8, 100, 70)">
        <ellipse cx="100" cy="70" rx="52" ry="42" fill="#F97316" />
        <circle cx="82" cy="64" r="10" fill="#fff" />
        <circle cx="118" cy="64" r="10" fill="#fff" />
        <circle cx="79" cy="62" r="5" fill="#0F172A" />
        <circle cx="121" cy="66" r="5" fill="#0F172A" />
        <path
          d="M110 50 Q118 44 128 48"
          stroke="#0F172A"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />
        <ellipse cx="100" cy="84" rx="5" ry="6" fill="#EA580C" />
      </g>

      <path
        d="M56 108 Q28 128 16 158 Q12 170 20 168"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        style={{ animation: "wiggle1 2s ease-in-out infinite", transformOrigin: "top" }}
      />
      <path
        d="M72 114 Q54 140 42 170 Q38 182 46 178"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        style={{ animation: "wiggle2 2.4s ease-in-out infinite", transformOrigin: "top" }}
      />
      <path
        d="M98 118 Q96 158 100 194"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M124 114 Q142 140 154 170 Q158 182 150 178"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        style={{ animation: "wiggle3 1.8s ease-in-out infinite", transformOrigin: "top" }}
      />
      <path
        d="M140 108 Q168 128 180 158 Q184 170 176 168"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        style={{ animation: "wiggle1 2s ease-in-out infinite", transformOrigin: "top" }}
      />

      <text
        x="140"
        y="28"
        fontSize="28"
        fontWeight="bold"
        fill="#F97316"
        opacity="0.6"
        style={{ animation: "float 2s ease-in-out infinite" }}
      >
        ?
      </text>
    </svg>
  );
}

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <style>{`
        @keyframes bob {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }
        @keyframes wiggle1 {
          0%, 100% { transform: rotate(0deg); }
          25% { transform: rotate(-3deg); }
          75% { transform: rotate(3deg); }
        }
        @keyframes wiggle2 {
          0%, 100% { transform: rotate(0deg); }
          25% { transform: rotate(4deg); }
          75% { transform: rotate(-4deg); }
        }
        @keyframes wiggle3 {
          0%, 100% { transform: rotate(0deg); }
          25% { transform: rotate(-5deg); }
          75% { transform: rotate(2deg); }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0); opacity: 0.6; }
          50% { transform: translateY(-6px); opacity: 0.3; }
        }
      `}</style>

      <LostOctopus />

      <p className="mt-8 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
        404 · not found
      </p>

      <p className="mt-3 font-display text-[28px] font-bold tracking-[-0.02em] text-ink">
        Nothing in the stash here.
      </p>

      <p className="mt-2 text-[15px] text-dim">
        This page doesn&apos;t exist, or it was moved.
      </p>

      <Link
        href="/"
        className="mt-8 inline-flex h-10 items-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
      >
        Back to home
      </Link>
    </div>
  );
}
