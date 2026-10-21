"use client";

import { useRef, useState, type PointerEvent } from "react";
import styles from "./ResearchLandscape.module.css";

export default function ResearchLandscape() {
  const scene = useRef<HTMLDivElement>(null);
  const [run, setRun] = useState(0);

  function move(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType !== "mouse") return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const offset = (event.clientX - bounds.left) / bounds.width - 0.5;
    scene.current?.style.setProperty("--drift", `${offset * 12}px`);
  }

  return (
    <div
      ref={scene}
      className={styles.scene}
      onPointerMove={move}
      onPointerLeave={() => scene.current?.style.setProperty("--drift", "0px")}
    >
      <svg className={styles.landscape} viewBox="0 0 1200 280" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <g className={styles.far}>
          <path fill="#cbd0d0" d="M-30 210 95 90 175 158 305 30 443 159 548 67 666 164 795 44 932 161 1050 82 1230 210V300H-30Z" />
          <path fill="#f7f4ee" d="m271 65 34-35 42 39-30-13-12 8-10-10Zm253 29 24-27 29 28-22-9-8 5-8-8Zm238-14 33-36 37 37-25-11-12 7-12-9Z" />
        </g>
        <g className={styles.near}>
          <path fill="#a9b69e" d="M-30 236 135 157 273 220 420 126 600 234 790 147 966 223 1100 161 1230 229V300H-30Z" />
          <path fill="#8fA389" d="M-30 256Q160 189 330 235T650 231T970 226T1230 236V300H-30Z" />
          <path fill="#c4cba8" d="M-30 260Q210 232 420 253T830 252T1230 245V300H-30Z" />
          <path fill="none" stroke="#e2e1c9" strokeWidth="2" d="M-30 271Q230 252 460 267T850 267T1230 260" />
          {[155, 173, 933, 950, 1020].map((x, i) => (
            <ellipse key={x} cx={x} cy={242 - (i % 2) * 4} rx="4" ry={13 + (i % 2) * 3} fill="#718667" />
          ))}
        </g>
        {run > 0 && (
          <g key={run}>
            <path className={styles.trail} d="M420 126C446 141 475 155 498 174S548 190 567 207 600 228 622 234" fill="none" stroke="#c4421f" strokeWidth="1.5" strokeDasharray="3 6" />
            <circle className={styles.point} r="5" fill="#ff5a36" stroke="#f7f4ee" strokeWidth="2" />
          </g>
        )}
      </svg>
      <div className={styles.controls}>
        <button type="button" onClick={() => setRun((value) => value + 1)} className={styles.button}>
          Follow the gradient <span aria-hidden="true">↘</span>
        </button>
        <a href="https://ferganalabs.com" className={styles.credit}>Fergana Labs · San Francisco</a>
      </div>
      <span className="sr-only" role="status">{run > 0 ? `Gradient descent ${run}: a point follows the slope into the valley.` : ""}</span>
    </div>
  );
}
