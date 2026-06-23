import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
import { resetSkillNavigationCache } from "../lib/skillNavigationCache";
import { getPins, getSidebar, listSources } from "../lib/api";

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
  getSidebar: vi.fn(),
  getPins: vi.fn(),
  setPins: vi.fn(),
  getMyRecents: vi.fn(),
  recordRecent: vi.fn(),
  listSources: vi.fn(),
}));

const user = {
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

function navLink(label: string): HTMLAnchorElement {
  const link = screen.getByText(label).closest("a");
  if (!link) throw new Error(`No link for ${label}`);
  return link as HTMLAnchorElement;
}

beforeEach(() => {
  nav.pathname = "/";
  localStorage.clear();
  resetSkillNavigationCache();
  vi.mocked(getSidebar).mockResolvedValue({
    sessions: [],
    files: { folders: [], pages: [], files: [] },
    skills: [],
  });
  vi.mocked(getPins).mockResolvedValue({ skills: [], sessions: [], files: [] });
  vi.mocked(listSources).mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AppSidebar nav", () => {
  it("links Skills, Sessions, and Files straight to their list pages", async () => {
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Skills")).toBeTruthy());

    expect(navLink("Skills").getAttribute("href")).toBe("/skills");
    expect(navLink("Agent Sessions").getAttribute("href")).toBe("/sessions");
    expect(navLink("Files").getAttribute("href")).toBe("/files");
    expect(navLink("Trash").getAttribute("href")).toBe("/trash");
  });

  it("labels the top nav Index and splits Your Brain from External Sources", async () => {
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Index")).toBeTruthy());

    expect(navLink("Index").getAttribute("href")).toBe("/activity");
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
    nav.pathname = "/folders/folder-1";
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Files")).toBeTruthy());

    expect(navLink("Files").className).toContain("color-brand-800");
    expect(navLink("Agent Sessions").className).not.toContain("color-brand-800");
  });
});
