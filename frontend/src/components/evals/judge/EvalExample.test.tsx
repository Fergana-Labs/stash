import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Eval, EvalExampleDetail } from "@/lib/evals-api";
import EvalExample from "./EvalExample";

const base = {
  id: "x1", item: { name: "", text: "Draft reply", trace: [], files: [] }, label: "good", note: "", source: "human",
  split: "train", message_id: null, created_at: new Date().toISOString(), added_by: "u1", added_by_name: "Sam",
  added_via: "api", caller: "claude-code", session_id: "s-1", session: null, call: null,
} as EvalExampleDetail;

const mocks = vi.hoisted(() => ({ evalExample: vi.fn() }));
vi.mock("@/lib/evals-api", async (actual) => ({
  ...(await actual<typeof import("@/lib/evals-api")>()),
  evalExample: mocks.evalExample,
  evalGet: vi.fn().mockResolvedValue({ id: "e", name: "Replies" } as Eval),
}));

it("shows who added an example, through which agent, and links its tracked session", async () => {
  mocks.evalExample.mockResolvedValue({ ...base, session: { session_id: "s-1", title: "Write replies", agent_name: "claude-code" } });
  render(<EvalExample evalId="e" exampleId="x1" />);
  expect(await screen.findByText("Sam")).toBeVisible();
  expect(screen.getByText("claude-code")).toBeVisible();
  expect(screen.getByText("API")).toBeVisible();
  expect(screen.getByRole("link", { name: "Write replies" })).toHaveAttribute("href", "/sessions/s-1");
  expect(screen.getByRole("link", { name: "Replies" })).toHaveAttribute("href", "/reward-models/evals/e?tab=examples");
});

it("shows a session Stash didn't track without a link", async () => {
  mocks.evalExample.mockResolvedValue({ ...base, caller: "", added_via: "web" });
  render(<EvalExample evalId="e" exampleId="x1" />);
  expect(await screen.findByText("s-1")).toBeVisible();
  expect(screen.queryByRole("link", { name: "s-1" })).toBeNull();
  expect(screen.queryByText("Agent")).toBeNull();
  expect(screen.getByText("App")).toBeVisible();
});
