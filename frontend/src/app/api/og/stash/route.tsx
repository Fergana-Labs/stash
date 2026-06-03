import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

import { loadPublicStashPreview } from "@/lib/stashPreviewFetch";
import {
  buildItemPreviewCard,
  buildStashPreviewCard,
  findStashItem,
  isStashItemType,
  type PreviewCard,
} from "@/lib/stashPreview";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const slug = request.nextUrl.searchParams.get("slug") ?? "";
  if (!slug) return new Response("Missing slug", { status: 400 });

  const data = await loadPublicStashPreview(slug);
  if (!data) return new Response("Stash not found", { status: 404 });

  const itemType = request.nextUrl.searchParams.get("type");
  const itemId = request.nextUrl.searchParams.get("id");
  const item =
    isStashItemType(itemType) && itemId ? findStashItem(data.items, itemType, itemId) : null;
  const card = item ? buildItemPreviewCard(data, item) : buildStashPreviewCard(data);

  return new ImageResponse(<PreviewImage card={card} />, {
    width: 1200,
    height: 630,
  });
}

function PreviewImage({ card }: { card: PreviewCard }) {
  const lines =
    card.lines.length > 0
      ? card.lines
      : [{ label: "Contents", meta: "Stash", excerpt: card.description }];
  const title = truncate(card.title, 76);
  const meta = [
    card.contentBadge,
    editedLabel(card.kind, card.updatedAt),
    card.workspaceName,
  ].filter(Boolean);
  const sideLabel = card.kind === "stash" ? "DETAILS" : "IN STASHES";
  const sideTitle =
    card.kind === "stash"
      ? card.workspaceName || "Workspace"
      : card.stashTitle;
  const sideMeta =
    card.kind === "stash"
      ? card.stats.slice(1, 4).join(" - ") || "Shared stash"
      : "1";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        position: "relative",
        background: "#FFFFFF",
        color: "#37352F",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          height: 68,
          display: "flex",
          alignItems: "center",
          borderBottom: "1px solid #ECECEA",
          background: "#FFFFFF",
        }}
      >
        <div
          style={{
            display: "flex",
            width: 245,
            paddingLeft: 26,
            fontSize: 18,
            fontWeight: 700,
            color: "#37352F",
          }}
        >
          {truncate(card.kind === "stash" ? card.title : card.stashTitle, 28)}
        </div>
        <div
          style={{
            width: 650,
            height: 42,
            display: "flex",
            alignItems: "center",
            border: "1px solid #E6E6E3",
            borderRadius: 22,
            background: "#FAFAF8",
            boxShadow: "0 1px 8px rgba(55, 53, 47, 0.10)",
            color: "#9B9A97",
            fontSize: 18,
            paddingLeft: 18,
            paddingRight: 18,
          }}
        >
          <SearchGlyph />
          <span style={{ display: "flex", marginLeft: 12 }}>
            Search {truncate(card.stashTitle, 44)}
          </span>
        </div>
        <div style={{ display: "flex", flex: 1 }} />
        <div
          style={{
            display: "flex",
            marginRight: 30,
            borderRadius: 22,
            background: "#EA580C",
            color: "#FFFFFF",
            fontSize: 18,
            fontWeight: 700,
            padding: "10px 18px",
          }}
        >
          Share
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          top: 68,
          bottom: 0,
          width: 176,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #ECECEA",
          background: "#FAFAF8",
        }}
      >
        <SidebarRow width={98} top={30} />
        <SidebarRow width={128} top={78} />
        <SidebarRow width={106} top={114} />
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 18,
            bottom: 92,
            height: 31,
            display: "flex",
            borderTopRightRadius: 16,
            borderBottomRightRadius: 16,
            background: "#FFF7ED",
          }}
        />
      </div>

      <div
        style={{
          position: "absolute",
          left: 176,
          right: 0,
          top: 68,
          bottom: 0,
          display: "flex",
          background: "#FFFFFF",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 0,
            height: 86,
            display: "flex",
            overflow: "hidden",
            background: "linear-gradient(90deg, #FED7AA, #FFEDD5, #FEF3C7)",
          }}
        >
          {card.coverImageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={card.coverImageUrl}
              alt=""
              width={1024}
              height={86}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
              }}
            />
          )}
        </div>

        <div
          style={{
            position: "absolute",
            left: 60,
            top: 50,
            width: 70,
            height: 70,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: "1px solid #ECECEA",
            borderRadius: 14,
            background: "#FFFFFF",
            boxShadow: "0 1px 4px rgba(55, 53, 47, 0.12)",
            color: "#EA580C",
          }}
        >
          {card.kind === "stash" && card.iconUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={card.iconUrl}
              alt=""
              width={70}
              height={70}
              style={{ width: 70, height: 70, objectFit: "cover" }}
            />
          ) : (
            <KindIcon kind={card.kind} size={39} />
          )}
        </div>

        <div
          style={{
            position: "absolute",
            left: 60,
            right: 54,
            top: 156,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", marginLeft: 16 }}>
            <div
              style={{
                display: "flex",
                width: 790,
                fontSize: 49,
                lineHeight: 1.1,
                letterSpacing: 0,
                fontWeight: 900,
                color: "#37352F",
              }}
            >
              {title}
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                marginTop: 22,
              }}
            >
              {meta.map((part, index) =>
                index === 0 ? (
                  <div
                    key={part}
                    style={{
                      display: "flex",
                      borderRadius: 6,
                      background: "#FFF7ED",
                      color: "#C2410C",
                      fontSize: 17,
                      fontWeight: 700,
                      letterSpacing: 1,
                      padding: "4px 9px",
                    }}
                  >
                    {part}
                  </div>
                ) : (
                  <div
                    key={part}
                    style={{
                      display: "flex",
                      marginLeft: 13,
                      fontSize: 18,
                      color: "#9B9A97",
                    }}
                  >
                    {part}
                  </div>
                ),
              )}
            </div>
          </div>
        </div>

        <div
          style={{
            position: "absolute",
            left: 104,
            top: 366,
            width: 570,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {card.kind === "stash" ? (
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div
                style={{
                  display: "flex",
                  fontSize: 33,
                  lineHeight: 1.18,
                  fontWeight: 900,
                  color: "#111111",
                }}
              >
                Contents
              </div>
              <div style={{ display: "flex", flexDirection: "column", marginTop: 16 }}>
                {lines.slice(0, 4).map((line) => (
                  <PreviewItemRow key={`${line.label}-${line.meta}`} line={line} />
                ))}
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div
                style={{
                  display: "flex",
                  fontSize: 34,
                  lineHeight: 1.18,
                  fontWeight: 900,
                  color: "#111111",
                }}
              >
                {truncate(card.bodyTitle || card.title, 68)}
              </div>
              <div
                style={{
                  display: "flex",
                  marginTop: 14,
                  fontSize: 21,
                  lineHeight: 1.42,
                  color: "#6B6860",
                }}
              >
                {truncate(card.bodyText || card.description, 260)}
              </div>
              <div
                style={{
                  display: "flex",
                  marginTop: 28,
                  height: 1,
                  width: 520,
                  background: "#ECECEA",
                }}
              />
              {lines[1] && (
                <div
                  style={{
                    display: "flex",
                    marginTop: 22,
                    fontSize: 25,
                    lineHeight: 1.25,
                    fontWeight: 800,
                    color: "#111111",
                  }}
                >
                  {truncate(lines[1].excerpt, 92)}
                </div>
              )}
            </div>
          )}
        </div>

        <div
          style={{
            position: "absolute",
            right: 48,
            top: 368,
            width: 314,
            minHeight: 122,
            display: "flex",
            flexDirection: "column",
            border: "1px solid #ECECEA",
            borderRadius: 14,
            background: "#F7F7F5",
            padding: 18,
          }}
        >
          <div
            style={{
              display: "flex",
              fontSize: 15,
              letterSpacing: 2,
              color: "#9B9A97",
              fontWeight: 700,
            }}
          >
            {sideLabel}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              marginTop: 16,
              border: "1px solid #ECECEA",
              borderRadius: 10,
              background: "#FFFFFF",
              padding: "13px 14px",
            }}
          >
            <div
              style={{
                display: "flex",
                width: 18,
                height: 18,
                color: "#EA580C",
                marginRight: 13,
              }}
            >
              <StashGlyph />
            </div>
            <div
              style={{
                display: "flex",
                flex: 1,
                fontSize: 18,
                fontWeight: 700,
                color: "#37352F",
              }}
            >
              {truncate(sideTitle, 24)}
            </div>
            <div style={{ display: "flex", fontSize: 15, color: "#9B9A97", marginLeft: 12 }}>
              {truncate(sideMeta, 14)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SidebarRow({ width, top }: { width: number; top: number }) {
  return (
    <div
      style={{
        position: "absolute",
        left: 24,
        top,
        width,
        height: 11,
        display: "flex",
        borderRadius: 5,
        background: "#EFEFEE",
      }}
    />
  );
}

function PreviewItemRow({ line }: { line: { label: string; meta: string; excerpt: string } }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        width: 520,
        borderTop: "1px solid #ECECEA",
        paddingTop: 10,
        paddingBottom: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          width: 22,
          height: 22,
          color: "#9B9A97",
          marginRight: 12,
        }}
      >
        <KindIcon kind="page" size={20} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
        <div style={{ display: "flex", fontSize: 17, fontWeight: 700, color: "#37352F" }}>
          {truncate(line.label, 38)}
        </div>
        <div style={{ display: "flex", marginTop: 3, fontSize: 13, color: "#9B9A97" }}>
          {truncate(line.meta || line.excerpt, 48)}
        </div>
      </div>
    </div>
  );
}

function SearchGlyph() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="11" cy="11" r="7" stroke="#9B9A97" strokeWidth="2" />
      <path d="M16.5 16.5L21 21" stroke="#9B9A97" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function KindIcon({ kind, size }: { kind: PreviewCard["kind"]; size: number }) {
  if (kind === "folder") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <path
          d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
          stroke="currentColor"
          strokeWidth="1.8"
        />
      </svg>
    );
  }

  if (kind === "session") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <path
          d="M21 12c0 4.4-4 8-9 8-1.4 0-2.8-.3-4-.8L3 21l1.5-4C3.6 15.7 3 13.9 3 12c0-4.4 4-8 9-8s9 3.6 9 8z"
          stroke="currentColor"
          strokeWidth="1.8"
        />
      </svg>
    );
  }

  if (kind === "table") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <path d="M3 10h18M3 16h18M9 4v16M15 4v16" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    );
  }

  if (kind === "stash") return <StashGlyph />;

  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.8" />
      {kind === "file" && (
        <path d="M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      )}
    </svg>
  );
}

function StashGlyph() {
  return (
    <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" shapeRendering="crispEdges">
      <g fill="currentColor">
        <rect x="8" y="4" width="8" height="2" />
        <rect x="6" y="6" width="12" height="8" />
        <rect x="4" y="9" width="2" height="5" />
        <rect x="18" y="9" width="2" height="5" />
        <rect x="5" y="14" width="3" height="3" />
        <rect x="10" y="14" width="2" height="5" />
        <rect x="14" y="14" width="2" height="5" />
        <rect x="17" y="14" width="3" height="3" />
      </g>
      <g fill="#FFFFFF">
        <rect x="9" y="8" width="2" height="2" />
        <rect x="13" y="8" width="2" height="2" />
      </g>
    </svg>
  );
}

function editedLabel(kind: PreviewCard["kind"], value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const label = kind === "stash" ? "Updated" : "Last edited";
  const formatted = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  return `${label} ${formatted}`;
}

function truncate(value: string, limit: number): string {
  const clean = value.replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 3).trimEnd()}...`;
}
