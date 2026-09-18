import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { getSourceStatus } from "@/lib/api";
import { SkillDocumentStatus, SourceRow } from "./page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getSourceStatus: vi.fn(),
}));

it("shows an active background sync neutrally and prevents a duplicate click", async () => {
  vi.mocked(getSourceStatus).mockResolvedValue({
    source: "src-1",
    type: "google_drive_folder",
    capability: "navigable",
    display_name: "Skills",
    sync_status: "syncing",
    last_synced_at: null,
    sync_error: null,
    item_count: 3,
  });
  const onSync = vi.fn();
  const view = render(
    <SourceRow
      source={{
        source: "src-1",
        type: "google_drive_folder",
        capability: "navigable",
        display_name: "Skills",
        sync_status: "syncing",
        sync_enabled: true,
      }}
      highlighted={false}
      open={false}
      busySync={false}
      busyDelete={false}
      busySkills={false}
      onOpen={vi.fn()}
      onSync={onSync}
      onToggleSkills={vi.fn()}
      onRemove={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "More actions" }));
  const syncing = screen.getByRole("menuitem", { name: "Sync in progress" });
  expect(syncing).toHaveAttribute("aria-disabled", "true");
  await userEvent.click(syncing);
  expect(onSync).not.toHaveBeenCalled();
  view.unmount();
});

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
