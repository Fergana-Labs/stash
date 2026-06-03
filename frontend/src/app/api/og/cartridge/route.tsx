import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

import { loadPublicCartridgePreview } from "@/lib/cartridgePreviewFetch";
import {
  buildItemPreviewCard,
  buildCartridgePreviewCard,
  findCartridgeItem,
  isCartridgeItemType,
  type PreviewCard,
} from "@/lib/cartridgePreview";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const slug = request.nextUrl.searchParams.get("slug") ?? "";
  if (!slug) return new Response("Missing slug", { status: 400 });

  const data = await loadPublicCartridgePreview(slug);
  if (!data) return new Response("Stash not found", { status: 404 });

  const itemType = request.nextUrl.searchParams.get("type");
  const itemId = request.nextUrl.searchParams.get("id");
  const item =
    isCartridgeItemType(itemType) && itemId ? findCartridgeItem(data.items, itemType, itemId) : null;
  const card = item ? buildItemPreviewCard(data, item) : buildCartridgePreviewCard(data);

  return new ImageResponse(<PreviewImage card={card} />, {
    width: 1200,
    height: 630,
  });
}

function PreviewImage({ card }: { card: PreviewCard }) {
  const lines = card.lines.length > 0 ? card.lines : [{ label: "Contents", meta: "Stash", excerpt: card.description }];

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        position: "relative",
        background: "#F8FAFC",
        color: "#111827",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(135deg, ${card.accent.wash} 0%, #FFFFFF 48%, #E0F2FE 100%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 44,
          right: 44,
          top: 42,
          bottom: 42,
          display: "flex",
          flexDirection: "column",
          border: "1px solid rgba(148, 163, 184, 0.5)",
          borderRadius: 30,
          background: "rgba(255, 255, 255, 0.92)",
          padding: 44,
          boxShadow: "0 28px 90px rgba(15, 23, 42, 0.12)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", marginBottom: 26 }}>
          <div
            style={{
              width: 54,
              height: 54,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 16,
              background: card.accent.primary,
              color: "#FFFFFF",
              fontSize: 30,
              fontWeight: 800,
            }}
          >
            S
          </div>
          <div style={{ display: "flex", flexDirection: "column", marginLeft: 16 }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#0F172A" }}>
              Stash
            </div>
            <div
              style={{
                marginTop: 3,
                fontSize: 18,
                fontWeight: 600,
                color: card.accent.primary,
              }}
            >
              {truncate(card.eyebrow, 76)}
            </div>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            fontSize: 54,
            lineHeight: 1.02,
            letterSpacing: 0,
            fontWeight: 800,
            color: "#0F172A",
            marginBottom: 18,
          }}
        >
          {truncate(card.title, 86)}
        </div>

        <div
          style={{
            display: "flex",
            fontSize: 25,
            lineHeight: 1.28,
            color: "#475569",
            marginBottom: 24,
          }}
        >
          {truncate(card.description, 150)}
        </div>

        <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
          {lines.slice(0, 3).map((line) => (
            <div
              key={`${line.meta}-${line.label}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                borderTop: "1px solid #E2E8F0",
                paddingTop: 14,
                paddingBottom: 13,
              }}
            >
              <div
                style={{
                  width: 138,
                  flexShrink: 0,
                  display: "flex",
                  flexDirection: "column",
                  marginRight: 20,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    fontSize: 17,
                    fontWeight: 800,
                    color: "#0F172A",
                  }}
                >
                  {truncate(line.label, 20)}
                </div>
                <div
                  style={{
                    display: "flex",
                    marginTop: 4,
                    fontSize: 14,
                    fontWeight: 700,
                    color: card.accent.secondary,
                    textTransform: "uppercase",
                  }}
                >
                  {truncate(line.meta, 24)}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  flex: 1,
                  fontSize: 20,
                  lineHeight: 1.28,
                  color: "#334155",
                }}
              >
                {truncate(line.excerpt, 145)}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", marginTop: 18 }}>
          {card.stats.slice(0, 4).map((stat) => (
            <div
              key={stat}
              style={{
                display: "flex",
                alignItems: "center",
                border: "1px solid #CBD5E1",
                borderRadius: 999,
                padding: "8px 13px",
                marginRight: 10,
                fontSize: 16,
                fontWeight: 700,
                color: "#334155",
                background: "#FFFFFF",
              }}
            >
              {truncate(stat, 32)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function truncate(value: string, limit: number): string {
  const clean = value.replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 3).trimEnd()}...`;
}
