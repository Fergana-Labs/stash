import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Eval, EvalCall } from "@/lib/evals-api";
import EvalDetail from "./EvalDetail";

const { call } = vi.hoisted(() => ({ call: {
  id: "c1", input: { name: "", text: "", trace: [], files: [] } as unknown as EvalCall["input"],
  mode: "change", score: 0.25, explanation: "The change made the header worse.", fixes: [],
  caller: "pr-bot", created_at: new Date().toISOString(), label: null, note: "",
  traits: [
    { trait: "No dashed lines", score: 0.25, why: "added a dashed border", touched: true, effect: "worse" },
    { trait: "Type hierarchy", score: null, why: "unchanged", touched: false, effect: null },
  ],
} as EvalCall }));

vi.mock("@/lib/evals-api", async (actual) => ({
  ...(await actual<typeof import("@/lib/evals-api")>()),
  evalGet: vi.fn().mockResolvedValue({
    id: "e", name: "UI", examples: { good: 0, bad: 0 }, unlabeled: 0, calls: 1, version: null, build: null,
  } as unknown as Eval),
  evalMessages: vi.fn().mockResolvedValue({ messages: [], busy: false }),
  evalCalls: vi.fn().mockResolvedValue([call]),
}));

it("shows a change's grade with only the traits the change touched", async () => {
  render(<EvalDetail id="e" />);
  fireEvent.click(await screen.findByRole("button", { name: /Agent calls/ }));
  expect(await screen.findByText("The change made the header worse.")).toBeVisible();
  expect(screen.getByText("Change")).toBeVisible();
  expect(screen.getByText("No dashed lines")).toBeVisible();
  expect(screen.getByText("worse")).toBeVisible();
  expect(screen.queryByText("Type hierarchy")).toBeNull();
});
