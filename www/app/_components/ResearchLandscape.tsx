"use client";

import { useState } from "react";
import styles from "./ResearchLandscape.module.css";

const HILLS = [
  { name: "Hill 1", x: 200, y: 142, shape: "M-80 320 200 142 480 320Z", route: "M370 310Q322 269 295 239T242 184L200 142" },
  { name: "Hill 2", x: 500, y: 72, shape: "M220 320 500 72 780 320Z", route: "M630 310Q612 248 577 211T532 133L500 72" },
  { name: "Hill 3", x: 800, y: 120, shape: "M520 320 800 120 1080 320Z", route: "M940 310Q902 257 880 235T837 171L800 120" },
];

export default function ResearchLandscape() {
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <section className={styles.scene} aria-label="Choose a hill to climb">
      <p className={styles.invitation}>Choose a hill to climb.</p>
      <div className={styles.valley}>
        <svg className={styles.landscape} viewBox="0 0 1000 320" preserveAspectRatio="none" aria-hidden="true">
          <path fill="#d7dbd7" d="M-20 230 80 100 190 220 360 28 510 206 660 44 810 218 970 75 1020 180V320H-20Z" />
          <path fill="#f7f4ee" d="m335 60 25-32 31 37-22-10-9 6-8-11Zm303 10 22-26 24 31-17-9-8 5-7-10Z" />
          {HILLS.map((hill, index) => (
            <path key={hill.name} className={styles.hill} fill={selected === index ? "#8dA184" : "#adb99f"} d={hill.shape} />
          ))}
          <path fill="#c4cba8" d="M-20 315Q220 297 410 312T760 309T1020 306V340H-20Z" />
          {selected !== null && (
            <g key={selected}>
              <path className={styles.route} d={HILLS[selected].route} fill="none" stroke="#3f5438" strokeWidth="2" pathLength="1" />
              <g className={styles.flag} transform={`translate(${HILLS[selected].x}, ${HILLS[selected].y})`}>
                <path d="M0 0V-23L15-18 0-13" fill="none" stroke="#3f5438" strokeWidth="2" strokeLinejoin="round" />
              </g>
            </g>
          )}
        </svg>
        {HILLS.map((hill, index) => (
          <button
            key={hill.name}
            type="button"
            className={styles.choice}
            style={{ left: `${hill.x / 10}%`, top: `${(hill.y + 38) / 3.2}%` }}
            aria-label={`Climb ${hill.name.toLowerCase()}`}
            aria-pressed={selected === index}
            onClick={() => setSelected(index)}
          >
            {hill.name}
          </button>
        ))}
      </div>
      <span className="sr-only" role="status">{selected !== null ? `${HILLS[selected].name} selected. The route climbs to its summit. Choose another hill to change direction.` : ""}</span>
    </section>
  );
}
