import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { listUploadSources, updateUploadSource } from "@/lib/api";
import DataAndPrivacy from "./DataAndPrivacy";

vi.mock("@/lib/api", () => ({
  listUploadSources: vi.fn(),
  updateUploadSource: vi.fn(),
}));

vi.mock("@/lib/scope-store", () => ({
  useScope: () => null,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DataAndPrivacy", () => {
  it("names each uploading coding agent and computer", async () => {
    vi.mocked(listUploadSources).mockResolvedValue({
      sources: [
        {
          client: "codex_cli",
          key_id: "key-codex",
          computer_name: "henrys-macbook-pro",
          session_count: 4,
          last_uploaded_at: new Date().toISOString(),
          uploads_enabled: true,
          can_manage: true,
        },
        {
          client: "claude_code",
          key_id: null,
          computer_name: null,
          session_count: 1,
          last_uploaded_at: new Date().toISOString(),
          uploads_enabled: null,
          can_manage: false,
        },
        {
          client: null,
          key_id: "key-mini",
          computer_name: "henrys-mac-mini",
          session_count: 0,
          last_uploaded_at: null,
          uploads_enabled: false,
          can_manage: true,
        },
      ],
    });

    render(<DataAndPrivacy />);

    expect(await screen.findByText("Codex on henrys-macbook-pro")).toBeTruthy();
    expect(screen.getByText("Claude Code on computer not recorded")).toBeTruthy();
    expect(screen.getByText("henrys-mac-mini")).toBeTruthy();
    expect(screen.getByText("Signed in · waiting for the next coding-agent upload")).toBeTruthy();
    expect(screen.getByText(/4 sessions/)).toBeTruthy();
    fireEvent.click(screen.getByRole("switch", { name: "Uploading" }));
    expect(updateUploadSource).toHaveBeenCalledWith("key-codex", false);
  });

  it("says when no CLI computers are signed in", async () => {
    vi.mocked(listUploadSources).mockResolvedValue({ sources: [] });
    render(<DataAndPrivacy />);
    expect(
      await screen.findByText("No CLI computers are signed in to this Stash yet.")
    ).toBeTruthy();
  });
});
