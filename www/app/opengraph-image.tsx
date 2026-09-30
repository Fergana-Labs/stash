import { ImageResponse } from "next/og";

export const alt = "Stash — agents that learn from the real world";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Branded social card: warm paper, the headline with its one accent word.
// Mirrors the page's identity, so it has to move when the brand moves.
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
          background: "#F7F4EE",
                    padding: "72px 80px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            fontSize: 26,
            color: "#16130F",
            fontWeight: 600,
          }}
        >
          <div style={{ width: 26, height: 26, borderRadius: 13, background: "#FF5A36" }} />
          Stash
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div
            style={{
              fontSize: 22,
              letterSpacing: 2,
              color: "#7C7469",
              fontFamily: "monospace",
            }}
          >
            memory infrastructure for agents
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              fontSize: 76,
              fontWeight: 600,
              lineHeight: 1.05,
              letterSpacing: -2,
              color: "#16130F",
            }}
          >
            Agents that learn from the&nbsp;
            <span style={{ color: "#FF5A36" }}>real world.</span>
          </div>
        </div>

        <div style={{ fontSize: 26, color: "#7C7469" }}>
          Open source · MIT licensed · Self-hostable
        </div>
      </div>
    ),
    size,
  );
}
