import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/types";
import Rail from "./rail";

const route = vi.hoisted(() => ({ pathname: "/", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: route.replace }),
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: Object.assign(
    (selector: (state: { setRailSection: () => void }) => unknown) =>
      selector({ setRailSection: vi.fn() }),
    { getState: () => ({ lastVfsUrl: null }) },
  ),
}));

vi.mock("@/components/workspace/account-menu", () => ({
  default: () => <button aria-label="Account" />,
}));

const user = { display_name: "Henry", name: "henry" } as User;

afterEach(() => {
  cleanup();
  route.replace.mockClear();
});

describe("Rail", () => {
  it("shows the requested sections in order", () => {
    render(<Rail user={user} onLogout={vi.fn()} />);

    const labels = Array.from(document.querySelectorAll("[aria-label]")).map(
      (element) => element.getAttribute("aria-label"),
    );
    expect(labels).toEqual([
      "Home",
      "Skills",
      "Sessions",
      "Session Analytics",
      "Files",
      "Viz",
      "Settings",
      "Account",
    ]);
  });

  it("opens analytics and viz as full-page destinations", () => {
    render(<Rail user={user} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByLabelText("Session Analytics"));
    expect(route.replace).toHaveBeenLastCalledWith("/sessions/analytics");

    fireEvent.click(screen.getByLabelText("Viz"));
    expect(route.replace).toHaveBeenLastCalledWith("/viz");
  });

  it("always opens Files at the flat index", () => {
    render(<Rail user={user} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByLabelText("Files"));

    expect(route.replace).toHaveBeenLastCalledWith("/files");
  });
});
