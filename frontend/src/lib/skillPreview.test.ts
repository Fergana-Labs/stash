import { describe, expect, it } from "vitest";
import {
  buildItemPreviewCard,
  buildSkillPreviewCard,
  findSkillItem,
  itemMetadataDescription,
  itemMetadataTitle,
  skillMetadataDescription,
  skillMetadataTitle,
  type SkillPreviewData,
} from "./skillPreview";

function detail(): SkillPreviewData {
  return {
    skill: {
      id: "skill-1",
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

describe("skill preview metadata", () => {
  it("builds skill-level titles and descriptions from item counts", () => {
    const data = detail();

    expect(skillMetadataTitle(data)).toBe("Launch Plan - Skill");
    expect(skillMetadataDescription(data)).toBe(
      "A Skill with 3 items: 1 page, 1 file, 1 session from Product.",
    );
  });

  it("builds item metadata from inlined page contents", () => {
    const data = detail();
    const item = data.items[0];

    expect(itemMetadataTitle(data, item)).toBe(
      "Announcement Draft - Launch Plan - Skill",
    );
    expect(itemMetadataDescription(data, item)).toContain(
      "The beta launch targets design partners first",
    );
  });

  it("matches session routes by session_id", () => {
    const data = detail();

    expect(findSkillItem(data.items, "session", "agent-session-1")?.label).toBe(
      "Launch research",
    );
  });

  it("builds preview cards with content lines", () => {
    const data = detail();
    const skillCard = buildSkillPreviewCard(data);
    const itemCard = buildItemPreviewCard(data, data.items[0]);

    expect(skillCard.lines.map((line) => line.label)).toContain("Announcement Draft");
    expect(itemCard.lines[0].excerpt).toContain("The beta launch targets");
  });

  it("uses visible HTML content for the product-style preview body", () => {
    const data = detail();
    const item = {
      object_type: "page" as const,
      object_id: "html-page-1",
      position: 0,
      label: "HTML Share",
      inline: {
        page: {
          name: "HTML Share",
          content_type: "html",
          content_html:
            "<html><head><title>Head Title</title><style>body{}</style></head><body><h1>Visible Heading</h1><p>Visible body copy.</p></body></html>",
          updated_at: "2026-06-02T06:53:17.953882+00:00",
        },
      },
    };

    const card = buildItemPreviewCard(data, item);

    expect(card.contentBadge).toBe("HTML");
    expect(card.bodyTitle).toBe("Visible Heading");
    expect(card.bodyText).toContain("Visible body copy");
    expect(card.bodyText).not.toContain("Head Title");
  });
});
