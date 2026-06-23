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
      owner_user_id: "user-1",
      slug: "launch-plan",
      title: "Launch Plan",
      description: "",
      owner_name: "henry",
      owner_display_name: "Henry",
    },
    folder_name: "Launch Plan",
    contents: {
      subfolders: [],
      pages: [
        {
          id: "page-1",
          name: "Announcement Draft",
          content_type: "markdown",
          content_markdown:
            "The beta launch targets design partners first. The public rollout follows after onboarding metrics settle.",
          content_html: "",
          folder_path: [],
        },
      ],
      files: [
        {
          id: "file-1",
          name: "pricing.pdf",
          content_type: "application/pdf",
          size_bytes: 2048,
          folder_path: [],
        },
      ],
      tables: [],
    },
  };
}

describe("skill preview metadata", () => {
  it("builds skill-level titles and descriptions from content counts", () => {
    const data = detail();

    expect(skillMetadataTitle(data)).toBe("Launch Plan - Skill");
    expect(skillMetadataDescription(data)).toBe(
      "A Skill with 2 files: 1 page, 1 file from Henry.",
    );
  });

  it("builds item metadata from inlined page contents", () => {
    const data = detail();
    const item = findSkillItem(data.contents, "page", "page-1");

    expect(item).not.toBeNull();
    expect(itemMetadataTitle(data, item!)).toBe(
      "Announcement Draft - Launch Plan - Skill",
    );
    expect(itemMetadataDescription(data, item!)).toContain(
      "The beta launch targets design partners first",
    );
  });

  it("finds files in the contents payload by id", () => {
    const data = detail();

    const item = findSkillItem(data.contents, "file", "file-1");
    expect(item?.item.name).toBe("pricing.pdf");
    expect(findSkillItem(data.contents, "file", "missing")).toBeNull();
  });

  it("builds preview cards with content lines", () => {
    const data = detail();
    const skillCard = buildSkillPreviewCard(data);
    const pageItem = findSkillItem(data.contents, "page", "page-1")!;
    const itemCard = buildItemPreviewCard(data, pageItem);

    expect(skillCard.lines.map((line) => line.label)).toContain("Announcement Draft");
    expect(itemCard.lines[0].excerpt).toContain("The beta launch targets");
  });

  it("uses visible HTML content for the product-style preview body", () => {
    const data = detail();
    data.contents.pages.push({
      id: "html-page-1",
      name: "HTML Share",
      content_type: "html",
      content_markdown: "",
      content_html:
        "<html><head><title>Head Title</title><style>body{}</style></head><body><h1>Visible Heading</h1><p>Visible body copy.</p></body></html>",
      updated_at: "2026-06-02T06:53:17.953882+00:00",
      folder_path: [],
    });

    const item = findSkillItem(data.contents, "page", "html-page-1")!;
    const card = buildItemPreviewCard(data, item);

    expect(card.contentBadge).toBe("HTML");
    expect(card.bodyTitle).toBe("Visible Heading");
    expect(card.bodyText).toContain("Visible body copy");
    expect(card.bodyText).not.toContain("Head Title");
  });
});
