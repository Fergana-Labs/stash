import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalWorkspace from "./EvalWorkspace";
import CreateEval from "./CreateEval";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imExamples: vi.fn(), imEditDraft: vi.fn(), evalPrepare: vi.fn(), imDraftRubric: vi.fn(), imGrade: vi.fn(), imFit: vi.fn(), imPromote: vi.fn(), evalAddExamples: vi.fn(), evalAddTrace: vi.fn(), imEditExample: vi.fn(), imPredict: vi.fn(), imPredictions: vi.fn(), imReview: vi.fn(), imCreate: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
vi.mock("./EvalInput", () => ({ default: ({ onChange }: { onChange: (item: string) => void }) => <textarea aria-label="Example output" onChange={(event) => onChange(event.target.value)} /> }));
vi.mock("@/components/intuitions/AgentUsagePanel", () => ({ default: () => <p>Connect</p> }));

const version = { id: "draft", status: "draft", number: 1, description: "Be helpful", labels: [{ id: "good" }, { id: "bad" }], rubric: [], head: null, head_stale: true, metrics: null, gate: null };
const detail = { model: { id: "eval", name: "Replies", output_type: "choice" }, draft: version, active: null, judge: { configured: true }, versions: [], counts: {} };

beforeEach(() => {
  vi.clearAllMocks(); api.imGet.mockResolvedValue(detail); api.imExamples.mockResolvedValue([]);
  api.imGrade.mockResolvedValue({ graded: 5, remaining: 0, failed: 0 });
  api.imDraftRubric.mockResolvedValue({ rubric: [{ id: "helpful", prompt: "Is it helpful?" }] });
  api.imPredictions.mockResolvedValue([]);
});

it("creates an eval from user criteria without trace-training settings", async () => {
  api.imCreate.mockResolvedValue({ model: { id: "created" } });
  const created = vi.fn(); render(<CreateEval onCreated={created} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: "Slides" } });
  fireEvent.change(screen.getByRole("textbox", { name: "What does good look like?" }), { target: { value: "Readable and concise" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to examples" }));
  await waitFor(() => expect(created).toHaveBeenCalledWith("created"));
  expect(api.imCreate).toHaveBeenCalledWith({ name: "Slides", description: "Readable and concise", output_type: "choice", labels: [{ id: "good", description: "Meets the user's expectations" }, { id: "bad", description: "Needs correction" }] });
  expect(screen.queryByRole("combobox", { name: /Base model|Epochs/ })).not.toBeInTheDocument();
});

it("prepares the held-out split before drafting criteria and fits only calibration data", async () => {
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Calibrate eval" }));
  await waitFor(() => expect(api.imFit).toHaveBeenCalledWith("eval", { train_on: "train", calibrate: true }));
  expect(api.evalPrepare.mock.invocationCallOrder[0]).toBeLessThan(api.imDraftRubric.mock.invocationCallOrder[0]);
  expect(api.imGrade.mock.invocationCallOrder[0]).toBeLessThan(api.imFit.mock.invocationCallOrder[0]);
  expect(api.imPromote).not.toHaveBeenCalled();
});

it("shows failed grading and does not calibrate or activate partial results", async () => {
  api.imGrade.mockResolvedValue({ graded: 2, remaining: 1, failed: 1, errors: ["Judge unavailable"] });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Calibrate eval" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Judge unavailable");
  expect(api.imFit).not.toHaveBeenCalled(); expect(api.imPromote).not.toHaveBeenCalled();
});

it("shows a held-out scorecard and requires review before overriding limited validation", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: { ...version, head: {}, head_stale: false, metrics: { eval: { n: 1, accuracy: 0, rows: [{ example_id: "held", label: "good", predicted: "bad", p_true: 0.3 }] } }, gate: { passed: false, checks: [{ name: "held_out_size", passed: false, detail: "1 held-out example; need 4" }] } } });
  api.imExamples.mockResolvedValue([{ id: "held", item: "A held-out slide", label: "good", split: "eval", note: "" }]);
  render(<EvalWorkspace id="eval" />);
  expect(await screen.findByText("0% agreement")).toBeVisible();
  expect(screen.getByText("Probability of your label: 30%")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Use this eval" }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("1 held-out example; need 4");
  expect(api.imPromote).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Activate anyway" }));
  await waitFor(() => expect(api.imPromote).toHaveBeenCalledWith("eval", true));
});

it("logs test calls through the prediction API and saves human corrections", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: { ...version, head: {}, head_stale: false } });
  api.imPredict.mockResolvedValue({ prediction_id: "call", label: "good", confidence: 0.8, probabilities: { good: 0.8, bad: 0.2 }, version: 1, rubric: {} });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Test eval" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Example output" }), { target: { value: "A reply" } });
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  expect(await screen.findByText("80% confidence · v1")).toBeVisible();
  expect(api.imPredict).toHaveBeenCalledWith("eval", "A reply", "draft");
  fireEvent.change(screen.getByRole("textbox", { name: "Score correction feedback" }), { target: { value: "Too vague" } });
  fireEvent.click(screen.getByRole("button", { name: "Mark bad" }));
  await waitFor(() => expect(api.imReview).toHaveBeenCalledWith("eval", "call", { label: "bad", note: "Too vague" }));
  expect(await screen.findByText("Correction saved as an example. Update the eval to include it.")).toBeVisible();
});
