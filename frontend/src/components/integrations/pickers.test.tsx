import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import type { Connector } from "./connectors";
import { AddSourceControls } from "./pickers";

const addSource = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    addSource: (...args: unknown[]) => addSource(...args),
  };
});

const getGitHubRepoAccess = vi.fn();
const setGitHubRepoAccess = vi.fn();
const listGitHubRepos = vi.fn();

vi.mock("@/lib/integrations", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/integrations")>();
  return {
    ...actual,
    getGitHubRepoAccess: (...args: unknown[]) => getGitHubRepoAccess(...args),
    setGitHubRepoAccess: (...args: unknown[]) => setGitHubRepoAccess(...args),
    listGitHubRepos: (...args: unknown[]) => listGitHubRepos(...args),
  };
});

const driveConnector: Connector = {
  provider: "google",
  label: "Google Drive",
  sourceType: "google_drive",
  kind: "drive",
  blurb: "",
};

function renderControls() {
  return render(
    <AddSourceControls connector={driveConnector} connected onAdded={() => {}} />
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Adding sources under a connection is unlimited — the pay gate lives on the
// connect step, not here. A failed add just surfaces the backend error inline.
describe("AddSourceControls", () => {
  it("surfaces the backend error inline, with no paywall", async () => {
    addSource.mockRejectedValue(new ApiError(400, "external_ref is required"));
    renderControls();

    fireEvent.click(screen.getByText("Add My Drive"));

    expect(await screen.findByText("external_ref is required")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// A customer scopes the knowledge base by connecting one Drive folder — the
// pasted link must become a source whose external_ref is that folder's id, so
// the indexer (and therefore the curator) only ever sees that subtree.
describe("DriveFolderControls", () => {
  it("adds a folder-scoped source from a pasted link, with the given name", async () => {
    addSource.mockResolvedValue({});
    renderControls();

    fireEvent.change(screen.getByPlaceholderText("Paste a Drive folder link"), {
      target: { value: "https://drive.google.com/drive/u/0/folders/1AbC_dEf-234567890?usp=sharing" },
    });
    fireEvent.change(screen.getByPlaceholderText("Name (e.g. Knowledge Base)"), {
      target: { value: "Heavi Knowledge Base" },
    });
    fireEvent.click(screen.getByText("Add folder"));

    expect(addSource).toHaveBeenCalledWith({
      source_type: "google_drive",
      external_ref: "1AbC_dEf-234567890",
      display_name: "Heavi Knowledge Base",
    });
  });

  it("accepts a bare folder id and defaults the name", async () => {
    addSource.mockResolvedValue({});
    renderControls();

    fireEvent.change(screen.getByPlaceholderText("Paste a Drive folder link"), {
      target: { value: "1AbC_dEf-234567890" },
    });
    fireEvent.click(screen.getByText("Add folder"));

    expect(addSource).toHaveBeenCalledWith({
      source_type: "google_drive",
      external_ref: "1AbC_dEf-234567890",
      display_name: "Google Drive folder",
    });
  });

  it("rejects non-folder input: button disabled, hint shown, nothing added", () => {
    renderControls();

    fireEvent.change(screen.getByPlaceholderText("Paste a Drive folder link"), {
      target: { value: "https://drive.google.com/file/d/xyz/view" },
    });
    fireEvent.click(screen.getByText("Add folder"));

    expect(addSource).not.toHaveBeenCalled();
    expect(screen.getByText(/doesn't look like a folder link/)).toBeTruthy();
  });
});

const githubConnector: Connector = {
  provider: "github",
  label: "GitHub",
  sourceType: "github_repo",
  kind: "github",
  blurb: "",
};

function renderGitHubControls() {
  return render(
    <AddSourceControls connector={githubConnector} connected onAdded={() => {}} />
  );
}

// The product promise is "your agent can see everything you can see" in one
// click: enabling all-repos mode is a single button, and leaving it is a
// single radio click that must actually turn the server-side mode off.
describe("GitHubAccessControls", () => {
  it("enables all-repos mode with one click", async () => {
    getGitHubRepoAccess.mockResolvedValue({ all_repos: false, total: null, created: null });
    listGitHubRepos.mockResolvedValue([
      { full_name: "acme/api", description: null, private: false, html_url: "", updated_at: null },
      { full_name: "acme/web", description: null, private: false, html_url: "", updated_at: null },
    ]);
    setGitHubRepoAccess.mockResolvedValue({ all_repos: true, total: 2, created: 2 });
    renderGitHubControls();

    fireEvent.click(await screen.findByRole("radio", { name: /All repositories/ }));
    fireEvent.click(await screen.findByText("Sync all 2 repositories"));

    expect(await screen.findByText(/sync automatically/)).toBeTruthy();
    expect(setGitHubRepoAccess).toHaveBeenCalledWith(true);
  });

  it("switching back to select repositories turns the mode off", async () => {
    getGitHubRepoAccess.mockResolvedValue({ all_repos: true, total: null, created: null });
    listGitHubRepos.mockResolvedValue([]);
    setGitHubRepoAccess.mockResolvedValue({ all_repos: false, total: null, created: null });
    renderGitHubControls();

    fireEvent.click(await screen.findByRole("radio", { name: /Only select repositories/ }));

    expect(await screen.findByPlaceholderText("Search repositories...")).toBeTruthy();
    expect(setGitHubRepoAccess).toHaveBeenCalledWith(false);
  });
});
