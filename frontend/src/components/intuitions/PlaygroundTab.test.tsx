import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import PlaygroundTab from "./PlaygroundTab";
vi.mock("./im-ui", async (importOriginal) => {
  const original = await importOriginal<typeof import("./im-ui")>();
  const version = { number: 2, head: {}, head_stale: false, rubric: [], labels: [{ id: "send", description: "Ready" }] };
  return { ...original, useIntuition: () => ({ id: "demo", detail: { model: { output_type: "choice" }, active: version, draft: null }, examples: [], goTo: vi.fn(), reload: vi.fn(), reloadExamples: vi.fn() }) };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
it("requires an input before running and keeps API instructions secondary", () => {
  render(<PlaygroundTab />);
  expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Upload a trace" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Input" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Output" })).toBeVisible();
  expect(screen.getByText("API access").closest("details")).not.toHaveAttribute("open");
  expect(screen.queryByText(/why the head decided/)).not.toBeInTheDocument();
});
