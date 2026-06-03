import { describe, expect, it } from "vitest";
import {
  buildItemPreviewCard,
  buildCartridgePreviewCard,
  findCartridgeItem,
  itemMetadataDescription,
  itemMetadataTitle,
  cartridgeMetadataDescription,
  cartridgeMetadataTitle,
  type CartridgePreviewData,
} from "./cartridgePreview";

function detail(): CartridgePreviewData {
  return {
    cartridge: {
      id: "stash-1",
      workspace_id: "workspace-1",
      slug: "launch-plan",
      title: "Launch Plan",
      description: "",
      owner_name: "henry",
      owner_display_name: "Henry",
    },
    workspace_name: "Product",
    items: [
      {
        object_type: "page",
        object_id: "page-1",
        position: 0,
        label: "Announcement Draft",
        inline: {
          page: {
            name: "Announcement Draft",
            content_type: "markdown",
            content_markdown:
              "The beta launch targets design partners first. The public rollout follows after onboarding metrics settle.",
          },
        },
      },
      {
        object_type: "file",
        object_id: "file-1",
        position: 1,
        label: "pricing.pdf",
        inline: {
          name: "pricing.pdf",
          content_type: "application/pdf",
          size_bytes: 2048,
        },
      },
      {
        object_type: "session",
        object_id: "session-row-1",
        position: 2,
        label: "Launch research",
        inline: {
          session: {
            session_id: "agent-session-1",
            agent_name: "codex",
            events: [
              {
                agent_name: "codex",
                event_type: "assistant_message",
                content: "I found three prior launch notes and summarized the risk areas.",
              },
            ],
          },
        },
      },
    ],
  };
}

describe("stash preview metadata", () => {
  it("builds stash-level titles and descriptions from item counts", () => {
    const data = detail();

    expect(cartridgeMetadataTitle(data)).toBe("Launch Plan - Stash");
    expect(cartridgeMetadataDescription(data)).toBe(
      "A Stash with 3 items: 1 page, 1 file, 1 session from Product.",
    );
  });

  it("builds item metadata from inlined page contents", () => {
    const data = detail();
    const item = data.items[0];

    expect(itemMetadataTitle(data, item)).toBe(
      "Announcement Draft - Launch Plan - Stash",
    );
    expect(itemMetadataDescription(data, item)).toContain(
      "The beta launch targets design partners first",
    );
  });

  it("matches session routes by session_id", () => {
    const data = detail();

    expect(findCartridgeItem(data.items, "session", "agent-session-1")?.label).toBe(
      "Launch research",
    );
  });

  it("builds preview cards with content lines", () => {
    const data = detail();
    const stashCard = buildCartridgePreviewCard(data);
    const itemCard = buildItemPreviewCard(data, data.items[0]);

    expect(stashCard.lines.map((line) => line.label)).toContain("Announcement Draft");
    expect(itemCard.lines[0].excerpt).toContain("The beta launch targets");
  });
});
