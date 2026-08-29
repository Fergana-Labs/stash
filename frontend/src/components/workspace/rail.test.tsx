import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/types";
import Rail from "./rail";

const route = vi.hoisted(() => ({
  pathname: "/",
  replace: vi.fn(),
  crumbs: null as
    { label: string; area?: "memory" | "skills" }[] | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: route.replace }),
  usePathname: () => route.pathname,
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

vi.mock("@/components/BreadcrumbContext", () => ({
  useBreadcrumbsValue: () => route.crumbs,
}));

vi.mock("@/components/workspace/account-menu", () => ({
  default: () => <button aria-label="Account" />,
}));

const user = { display_name: "Henry", name: "henry" } as User;

afterEach(() => {
  cleanup();
  route.replace.mockClear();
  route.pathname = "/";
  route.crumbs = null;
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
      "Usage",
      "Settings",
      "Account",
    ]);
  });

  it("opens Usage as a full-page destination", () => {
    render(<Rail user={user} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByLabelText("Usage"));
    expect(route.replace).toHaveBeenLastCalledWith("/sessions/analytics");
  });

  it("identifies Memory content with Home", () => {
    route.pathname = "/folders/memory";
    route.crumbs = [{ label: "Memory", area: "memory" }];

    render(<Rail user={user} onLogout={vi.fn()} />);

    expect(screen.getByLabelText("Home").className).toContain("text-brand-600");
    expect(screen.getByLabelText("Skills").className).not.toContain(
      "text-brand-600",
    );
  });

  it("identifies Skill content with Skills", () => {
    route.pathname = "/p/supporting-page";
    route.crumbs = [{ label: "Skills", area: "skills" }];

    render(<Rail user={user} onLogout={vi.fn()} />);

    expect(screen.getByLabelText("Skills").className).toContain(
      "text-brand-600",
    );
    expect(screen.getByLabelText("Home").className).not.toContain(
      "text-brand-600",
    );
  });
});
