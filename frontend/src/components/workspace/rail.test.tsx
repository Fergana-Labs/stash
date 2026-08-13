// The rail is the app's whole navigation surface, and its five sections are a
// claim about where content lives: Sessions and Skills are VFS mounts, not
// destinations of their own. If a session route stopped lighting up the VFS
// button, the user would be inside a section the rail says they aren't in.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import Rail from "./rail";
import type { User } from "@/lib/types";

const route = vi.hoisted(() => ({ pathname: "/", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: route.replace }),
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: Object.assign(
    (selector: (s: { setRailSection: () => void }) => unknown) =>
      selector({ setRailSection: vi.fn() }),
    { getState: () => ({ lastVfsUrl: null }) },
  ),
}));

const user = { display_name: "Henry", email: "henry@ferganalabs.com", name: "henry" } as User;

function renderAt(pathname: string) {
  route.pathname = pathname;
  render(<Rail user={user} onLogout={vi.fn()} />);
}

/** The label of the section the rail is showing as current. */
function currentSection(): string | null {
  const current = document.querySelector('[aria-current="page"]');
  return current?.getAttribute("aria-label") ?? null;
}

afterEach(() => {
  cleanup();
  route.replace.mockClear();
});

describe("Rail", () => {
  it("offers exactly the five sections", () => {
    renderAt("/");
    const labels = Array.from(document.querySelectorAll("[aria-label]")).map((el) =>
      el.getAttribute("aria-label"),
    );
    expect(labels).toEqual(["Integrations", "Home", "Viz", "VFS", "Chat", "Settings"]);
  });

  it("shows sessions as part of the VFS, not a section of their own", () => {
    renderAt("/sessions/abc");
    expect(currentSection()).toBe("VFS");
    expect(screen.queryByLabelText("Sessions")).toBeNull();
  });

  it("shows an opened skill as part of the VFS", () => {
    renderAt("/skills/folder/abc");
    expect(currentSection()).toBe("VFS");
    expect(screen.queryByLabelText("Skills")).toBeNull();
  });

  it("lights up Integrations on a provider page", () => {
    renderAt("/integrations/slack");
    expect(currentSection()).toBe("Integrations");
  });

  it("lights up Viz on the visualizations page", () => {
    renderAt("/viz");
    expect(currentSection()).toBe("Viz");
  });
});
