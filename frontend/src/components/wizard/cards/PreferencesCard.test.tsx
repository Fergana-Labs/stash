import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { TasteExample, TasteWorkspace } from "@/lib/taste-api";
import { WizardProvider } from "../wizard-ui";
import WebsiteEvalCard from "./WebsiteEvalCard";

const api = vi.hoisted(() => ({ get: vi.fn(), review: vi.fn() }));
vi.mock("@/lib/taste-api", () => ({
  tasteGet: api.get,
  tasteReview: api.review,
  tasteImage: () => new Promise(() => {}),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const example = (id: string, over: Partial<TasteExample>) => ({ id, label: "liked", usable: true, needs_clarification: false, quote: "", note: "", reason: "", ...over }) as TasteExample;
const workspace = (examples: TasteExample[], gaps: string[] = []) =>
  ({ examples, labels: { liked: 1, disliked: 0, build_gaps: gaps } }) as unknown as TasteWorkspace;

it("shows learned preferences and asks about unclear examples with buttons, not chat", async () => {
  const unclear = example("u1", { usable: false, needs_clarification: true, quote: "can you make this less vibed?" });
  const liked = example("l1", { quote: "check out this codex ui. that's goals" });
  api.get.mockResolvedValueOnce(workspace([liked, unclear], ["I need an example you clearly wanted changed."]));
  api.get.mockResolvedValueOnce(workspace([liked, { ...unclear, usable: true, needs_clarification: false, label: "disliked" }]));
  api.review.mockResolvedValue({});
  const send = vi.fn();
  render(
    <WizardProvider value={{ modelId: "eval", send, refresh: vi.fn(), version: 0, busy: false }}>
      <WebsiteEvalCard section="preferences" />
    </WizardProvider>,
  );
  expect(await screen.findByText("I need an example you clearly wanted changed.")).toBeTruthy();
  expect(screen.getByText("Needs your call · 1")).toBeTruthy();
  expect(screen.getByText("check out this codex ui. that's goals")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Change this" }));
  await waitFor(() => expect(send).toHaveBeenCalledWith(expect.stringContaining("website_eval finish"), "event"));
  expect(api.review).toHaveBeenCalledWith("u1", "disliked", "");
  expect(screen.queryByText(/Needs your call/)).toBeNull();
});
