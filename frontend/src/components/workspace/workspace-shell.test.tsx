import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/types";
import WorkspaceShell from "./workspace-shell";

vi.mock("@/lib/scope-store", () => ({ useScope: () => null }));
vi.mock("@/components/ShellChromeContext", () => ({
  useShellChromeValue: () => ({ shareAction: <button>Share</button> }),
}));
vi.mock("@/components/developer/DeveloperShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("./topbar", () => ({ default: () => <header>Topbar</header> }));
vi.mock("./rail", () => ({ default: () => <nav>Rail</nav> }));

afterEach(cleanup);

describe("WorkspaceShell", () => {
  it("renders route content directly without a tab strip", () => {
    render(
      <WorkspaceShell user={{} as User} onLogout={vi.fn()}>
        <div>Route content</div>
      </WorkspaceShell>,
    );

    expect(screen.getByText("Route content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });
});
