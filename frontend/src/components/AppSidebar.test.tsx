import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
import { resetSkillNavigationCache } from "../lib/skillNavigationCache";
import {
  getWorkspacePins,
  getWorkspaceSidebar,
  listMyWorkspaces,
  listWorkspaceSources,
} from "../lib/api";

const nav = vi.hoisted(() => ({
  pathname: "/",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    ...props
  }: {
    href: string;
    children: ReactNode;
    onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  }) => (
    <a
      href={href}
      {...props}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
    >
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  getWorkspaceSidebar: vi.fn(),
  listMyWorkspaces: vi.fn(),
  getWorkspacePins: vi.fn(),
  setWorkspacePins: vi.fn(),
  getWorkspaceRecents: vi.fn(),
  recordWorkspaceRecent: vi.fn(),
  listWorkspaceSources: vi.fn(),
}));

const user = {
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

const workspace = {
  id: "ws-1",
  name: "Demo Skill",
  description: "",
  creator_id: "user-1",
  invite_code: "invite",
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  member_count: 1,
};

function navLink(label: string): HTMLAnchorElement {
  const link = screen.getByText(label).closest("a");
  if (!link) throw new Error(`No link for ${label}`);
  return link as HTMLAnchorElement;
}

beforeEach(() => {
  nav.pathname = "/workspaces/ws-1";
  localStorage.clear();
  resetSkillNavigationCache();
  vi.mocked(listMyWorkspaces).mockResolvedValue({ workspaces: [workspace] });
  vi.mocked(getWorkspaceSidebar).mockResolvedValue({
    sessions: [],
    files: { folders: [], pages: [], files: [] },
    skills: [],
  });
  vi.mocked(getWorkspacePins).mockResolvedValue({ skills: [], sessions: [], files: [] });
  vi.mocked(listWorkspaceSources).mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AppSidebar workspace nav", () => {
  it("links Skills, Sessions, and Files straight to their list pages", async () => {
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Skills")).toBeTruthy());

    expect(navLink("Skills").getAttribute("href")).toBe("/workspaces/ws-1/skills");
    expect(navLink("Agent Sessions").getAttribute("href")).toBe("/workspaces/ws-1/sessions");
    expect(navLink("Files").getAttribute("href")).toBe("/workspaces/ws-1/files");
    expect(navLink("Trash").getAttribute("href")).toBe("/workspaces/ws-1/trash");
  });

  it("labels the top nav Index and splits Your Brain from External Sources", async () => {
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Index")).toBeTruthy());

    expect(navLink("Index").getAttribute("href")).toBe("/activity");
    // The section headers render only after the workspace fetch resolves,
    // later than the Index link — await them or this test flakes under load.
    expect(await screen.findByText("Your Brain")).toBeTruthy();
    // The External Sources header renders even with no connected sources.
    expect(await screen.findByText("External Sources")).toBeTruthy();
  });

  it("links Discover in the global nav", async () => {
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Discover")).toBeTruthy());

    expect(navLink("Discover").getAttribute("href")).toBe("/discover");
  });

  it("does not render native <details> trees for the sections", async () => {
    const { container } = render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Files")).toBeTruthy());

    expect(container.querySelector("details")).toBeNull();
  });

  it("marks the Files section active when viewing a file route", async () => {
    nav.pathname = "/workspaces/ws-1/folders/folder-1";
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Files")).toBeTruthy());

    expect(navLink("Files").className).toContain("color-brand-800");
    expect(navLink("Agent Sessions").className).not.toContain("color-brand-800");
  });
});
