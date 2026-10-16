import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import WebsiteEvalCard from "./WebsiteEvalCard";
const api = vi.hoisted(() => ({
  get: vi.fn(),
  image: vi.fn(),
  review: vi.fn(),
  send: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/taste-api", () => ({
  tasteGet: api.get,
  tasteImage: api.image,
  tasteReview: api.review,
  tasteInspect: vi.fn(),
  tasteCheckpoint: vi.fn(),
  tasteCompare: vi.fn(),
}));
vi.mock("../wizard-ui", async (original) => ({
  ...(await original<typeof import("../wizard-ui")>()),
  useWizard: () => ({ send: api.send, refresh: api.refresh, busy: false }),
}));
const id = "a".repeat(64);
function state() {
  return {
    id: "workspace",
    model_id: "eval",
    name: "Website design",
    reviewed: 0,
    examples: [
      {
        id,
        label: "disliked",
        suggested_label: "disliked",
        reviewed: false,
        quote: "Please remove the cards",
        note: "",
        partition: "train",
        reference: false,
      },
    ],
    grader: { version: "probe-v1", parameters: 2049, released: false },
    blockers: ["Needs validation"],
    jobs: [],
    trials: [],
    predictions: [],
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.get.mockResolvedValue(state());
  api.image.mockResolvedValue({ data_url: "data:image/png;base64,AA==" });
  api.review.mockResolvedValue({
    ...state(),
    reviewed: 1,
    examples: [{ ...state().examples[0], reviewed: true, label: "liked" }],
  });
});
it("reviews pixels inline without a separate navigation or search form", async () => {
  render(<WebsiteEvalCard />);
  expect(await screen.findByText("Please remove the cards")).toBeVisible();
  expect(
    screen.queryByRole("textbox", { name: /search/i }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Keep this" }));
  await waitFor(() => expect(api.review).toHaveBeenCalledWith(id, "liked", ""));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(api.send).toHaveBeenCalledWith(
    expect.stringContaining("Continue using my saved labels"),
    "event",
  );
});
it("asks the wizard agent to run experiments instead of launching from another workflow", async () => {
  render(<WebsiteEvalCard section="experiments" />);
  await screen.findByText(/GEPA changes instructions/);
  fireEvent.click(screen.getByRole("button", { name: "Run GEPA" }));
  expect(api.send).toHaveBeenCalledWith(
    expect.stringContaining("independent GEPA"),
  );
  expect(
    screen.getByText(/Both optimization experiments are blocked/),
  ).toBeVisible();
});
it("continues the agent conversation once when a durable background job finishes", async () => {
  api.get.mockResolvedValue({
    ...state(),
    jobs: [
      {
        id: "job-1",
        operation: "build",
        status: "succeeded",
        progress: "Completed",
      },
    ],
  });
  render(<WebsiteEvalCard section="progress" jobId="job-1" />);
  await waitFor(() => expect(api.send).toHaveBeenCalledTimes(1));
  expect(api.send).toHaveBeenCalledWith(
    expect.stringContaining("Read website_eval status and continue"),
    "event",
  );
  expect(sessionStorage.getItem("website-eval-job:job-1")).toBe("seen");
});
