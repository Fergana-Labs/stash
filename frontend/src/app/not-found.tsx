import Link from "next/link";

function LostOctopus() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 220"
      width={200}
      height={220}
      aria-hidden="true"
      className="animate-bob"
    >
      {/* Body — tilted slightly to look confused */}
      <g transform="rotate(-8, 100, 70)">
        <ellipse cx="100" cy="70" rx="52" ry="42" fill="#F97316" />

        {/* Eyes — one raised eyebrow, pupils looking different directions */}
        <circle cx="82" cy="64" r="10" fill="#fff" />
        <circle cx="118" cy="64" r="10" fill="#fff" />
        {/* Left pupil looking up-left */}
        <circle cx="79" cy="62" r="5" fill="#0F172A" />
        {/* Right pupil looking down-right */}
        <circle cx="121" cy="66" r="5" fill="#0F172A" />

        {/* Raised eyebrow on the right */}
        <path
          d="M110 50 Q118 44 128 48"
          stroke="#0F172A"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />

        {/* Little "o" mouth — surprised */}
        <ellipse cx="100" cy="84" rx="5" ry="6" fill="#EA580C" />
      </g>

      {/* Tentacles — reaching out in all directions, searching */}
      {/* Left outer — reaching way left with a curl */}
      <path
        d="M56 108 Q28 128 16 158 Q12 170 20 168"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        className="animate-wiggle-1"
      />
      {/* Left inner */}
      <path
        d="M72 114 Q54 140 42 170 Q38 182 46 178"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        className="animate-wiggle-2"
      />
      {/* Center — drooping down sadly */}
      <path
        d="M98 118 Q96 158 100 194"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
      />
      {/* Right inner */}
      <path
        d="M124 114 Q142 140 154 170 Q158 182 150 178"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        className="animate-wiggle-3"
      />
      {/* Right outer — reaching way right with a curl */}
      <path
        d="M140 108 Q168 128 180 158 Q184 170 176 168"
        stroke="#F97316"
        strokeWidth="8"
        strokeLinecap="round"
        fill="none"
        className="animate-wiggle-1"
      />

      {/* Question mark floating above head */}
      <text
        x="140"
        y="28"
        fontSize="28"
        fontWeight="bold"
        fill="#F97316"
        opacity="0.6"
        className="animate-float"
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
        .animate-bob { animation: bob 3s ease-in-out infinite; }
        .animate-wiggle-1 { animation: wiggle1 2s ease-in-out infinite; transform-origin: top; }
        .animate-wiggle-2 { animation: wiggle2 2.4s ease-in-out infinite; transform-origin: top; }
        .animate-wiggle-3 { animation: wiggle3 1.8s ease-in-out infinite; transform-origin: top; }
        .animate-float { animation: float 2s ease-in-out infinite; }
      `}</style>

      <LostOctopus />

      <p className="mt-6 font-mono text-[80px] font-bold leading-none tracking-tighter text-brand">
        404
      </p>

      <p className="mt-3 font-display text-xl font-medium text-foreground">
        This page got lost at sea
      </p>

      <p className="mt-1.5 text-sm text-dim">
        Our octopus searched all eight arms and couldn&apos;t find it.
      </p>

      <Link
        href="/"
        className="mt-8 inline-flex h-10 items-center rounded-md bg-brand px-5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-hover"
      >
        Back to shore
      </Link>
    </div>
  );
}
