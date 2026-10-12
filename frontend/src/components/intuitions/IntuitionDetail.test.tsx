import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import IntuitionDetail from "./IntuitionDetail";

const { route } = vi.hoisted(() => ({ route: { tab: "" } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/reward-models/models/sandbox/model",
  useSearchParams: () => new URLSearchParams({ tab: route.tab }),
}));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/lib/intuition-api", () => ({
  imGet: vi.fn(async () => ({ model: { name: "Preview" }, active: null, draft: null, counts: { total: 0, inbox: 0, needs_review: 0 } })),
  imExamples: vi.fn(async () => []),
}));
vi.mock("./IntuitionHeader", () => ({ default: () => null }));
vi.mock("./PlaygroundTab", () => ({ default: () => <p>Trace playground</p> }));
vi.mock("./InboxTab", () => ({ default: () => null }));
vi.mock("./ExamplesTab", () => ({ default: () => null }));
vi.mock("./VersionsTab", () => ({ default: () => null }));

it.each(["rubric", "train"])("opens the playground for a retired %s tab URL", async (tab) => {
  route.tab = tab;
  render(<IntuitionDetail id="model" />);
  expect(await screen.findByText("Trace playground")).toBeVisible();
  expect(screen.getByRole("tab", { name: "Playground" })).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByRole("tab", { name: "Rubric" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "Train" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("tab")).toHaveLength(4);
});
