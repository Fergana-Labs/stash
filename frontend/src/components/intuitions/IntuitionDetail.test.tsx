import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import IntuitionDetail from "./IntuitionDetail";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/lib/intuition-api", () => ({
  imGet: vi.fn(async () => ({ model: { name: "Preview" }, active: null, draft: null, counts: { total: 0, inbox: 0, needs_review: 0 } })),
}));
vi.mock("./IntuitionHeader", () => ({ default: () => null }));
vi.mock("./PlaygroundTab", () => ({ default: () => <p>Trace playground</p> }));

it.each(["playground", "rubric", "train", "inbox", "examples", "versions"])("opens the playground without section tabs for tab=%s", async (tab) => {
  window.history.replaceState(null, "", `/reward-models/models/sandbox/model?tab=${tab}`);
  render(<IntuitionDetail id="model" />);
  expect(await screen.findByText("Trace playground")).toBeVisible();
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
});

it("embeds the compatible sandbox without overriding the list breadcrumbs", async () => {
  vi.mocked(useBreadcrumbs).mockClear();
  render(<IntuitionDetail id="model" embedded />);
  expect(await screen.findByText("Trace playground")).toBeVisible();
  expect(useBreadcrumbs).not.toHaveBeenCalled();
});
