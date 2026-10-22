import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import WebsiteEvalCard from "./WebsiteEvalCard";
const api = vi.hoisted(() => ({ get: vi.fn(), send: vi.fn(), router: {replace: vi.fn()} }));
vi.mock("next/navigation", () => ({useRouter: () => api.router}));
vi.mock("@/lib/taste-api", () => ({ tasteGet: api.get }));
vi.mock("../wizard-ui", async (original) => ({
  ...(await original<typeof import("../wizard-ui")>()),
  useWizard: () => ({ send: api.send }),
}));
const state = () => ({
  endpoint: {
    ready: true,
    path: "/api/v1/intuitions/eval/predict",
    quality_note: "Accuracy has not been independently established yet.",
  },
  jobs: [],
});
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.get.mockResolvedValue(state());
});
it("ends with the endpoint even when independent accuracy evidence is missing", async () => {
  render(<WebsiteEvalCard section="connect" />);
  expect(await screen.findByText("Your eval is ready")).toBeVisible();
  expect(
    screen.getByText("http://localhost:3000/api/v1/intuitions/eval/predict"),
  ).toBeVisible();
  expect(
    screen.getByText("Accuracy has not been independently established yet."),
  ).toBeVisible();
  expect(screen.queryByText(/blocked until/)).not.toBeInTheDocument();
  expect(api.send).not.toHaveBeenCalled();
});
it("renders persisted research cards as the same simple endpoint with no experiment choices", async () => {
  render(<WebsiteEvalCard section="experiments" />);
  await screen.findByText("Your eval is ready");
  for (const name of [
    "Write the skill",
    "Run GEPA",
    "Refine weights",
    "Compare results",
    "Continue",
  ])
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  expect(screen.queryByText(/GEPA/)).not.toBeInTheDocument();
});
it("continues automatically after collection without making the user choose an action", async () => {
  api.get.mockResolvedValue({
    endpoint: { ready: false, path: null },
    jobs: [{ id: "job-1", operation: "collect_all", status: "succeeded" }],
  });
  render(<WebsiteEvalCard section="progress" jobId="job-1" />);
  await waitFor(() => expect(api.send).toHaveBeenCalledTimes(1));
  expect(api.send).toHaveBeenCalledWith(
    "Finished learning from your examples.",
    "event",
  );
  expect(
    screen.queryByRole("button", { name: "Continue" }),
  ).not.toBeInTheDocument();
});

it("opens the endpoint automatically when background setup has published it", async () => {
  api.get.mockResolvedValue({...state(), published: true, model_id: "eval"});
  render(<WebsiteEvalCard section="progress" jobId="job-1" />);
  await waitFor(() => expect(api.router.replace).toHaveBeenCalledWith("/reward-models/evals/eval"));
  expect(api.send).not.toHaveBeenCalled();
});
