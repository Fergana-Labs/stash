import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SkillDocumentStatus } from "./page";

describe("SkillDocumentStatus", () => {
  it("shows whether a file is a Skill and explains why", () => {
    render(
      <SkillDocumentStatus
        entry={{
          name: "notes.md",
          kind: "document",
          skill_status: "not_skill",
          skill_status_reason: "At the top, add a name and description between --- lines.",
        }}
      />,
    );

    expect(screen.getByText("Not a Skill")).toBeInTheDocument();
    expect(
      screen.getByText("At the top, add a name and description between --- lines."),
    ).toBeInTheDocument();
  });

  it("does not add a status to files in regular folders", () => {
    const { container } = render(
      <SkillDocumentStatus entry={{ name: "notes.md", kind: "document" }} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
