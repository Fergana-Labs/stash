import { ImageResponse } from "next/og";

export const alt = "Stash — give your agents a memory that compounds";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Branded social card: warm paper, the mono bracket kicker, the headline with
// the one orange accent. Mirrors the page's typographic identity.
export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#FBFAF8",
          backgroundImage: "radial-gradient(rgba(26,23,20,0.06) 1.5px, transparent 1.5px)",
          backgroundSize: "32px 32px",
          padding: "72px 80px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            fontSize: 26,
            color: "#1A1714",
            fontWeight: 700,
          }}
        >
          <div style={{ width: 26, height: 26, borderRadius: 13, background: "#F97316" }} />
          stash
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div
            style={{
              fontSize: 22,
              letterSpacing: 6,
              color: "#6B655B",
              fontFamily: "monospace",
            }}
          >
            [ MEMORY.FOR.AGENTS ]
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              fontSize: 76,
              fontWeight: 700,
              lineHeight: 1.05,
              letterSpacing: -2,
              color: "#1A1714",
            }}
          >
            Give your agents a memory that&nbsp;
            <span style={{ color: "#F97316" }}>compounds.</span>
          </div>
        </div>

        <div style={{ fontSize: 26, color: "#6B655B" }}>
          Open source · MIT licensed · Self-hostable
        </div>
      </div>
    ),
    size,
  );
}
