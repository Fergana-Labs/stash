import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImageEvalDetail from "@/components/image-eval/ImageEvalDetail";
import * as api from "@/lib/image-eval-api";

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: () => undefined }));
vi.mock("@/components/image-eval/ImageEvalImage", () => ({ default: ({ alt }: { alt: string }) => <span>{alt}</span> }));
vi.mock("@/lib/image-eval-api", async (original) => ({
  ...(await original<typeof import("@/lib/image-eval-api")>()),
  imageEvalGet: vi.fn(), imageEvalExamples: vi.fn(), imageEvalCalls: vi.fn(), imageEvalLabelCall: vi.fn(), imageEvalTrain: vi.fn(),
}));

const detail = {
  id: "c1", model_id: null, name: "Yoko", description: "", style_brief: "- hair is built from small loops", build: { stage: "done" as const }, trained: true, trained_at: "2026-10-22T07:00:00Z",
  heldout_accuracy: 0.97, heldout_balanced_accuracy: 0.96, heldout_method: "leave-one-out", liked: 34, disliked: 35,
  created_at: "2026-10-22T06:00:00Z", updated_at: "2026-10-22T07:00:00Z",
  examples: { liked: 34, disliked: 35, imitations: 12 }, calls: 2, needs_training: false,
};
const call = (id: string, score: number) => ({
  id, caller: "draw-agent", task: "cat explaining MCP", score, created_at: "2026-10-22T07:10:00Z",
  comments: { summary: "Lines too thin", fixes: [{ issue: "Hair is one outline", fix: "Build it from small loops" }], keep: [] },
  feedback_label: null, feedback_note: null,
});

describe("ImageEvalDetail", () => {
  beforeEach(() => {
    vi.mocked(api.imageEvalGet).mockResolvedValue(detail);
    vi.mocked(api.imageEvalExamples).mockResolvedValue([]);
    vi.mocked(api.imageEvalCalls).mockResolvedValue([call("k2", 0.81), call("k1", 0.62)]);
    vi.mocked(api.imageEvalLabelCall).mockResolvedValue({ call_id: "k1" });
  });

  it("shows accuracy, each call's fixes, and the score across an agent's drafts", async () => {
    render(<ImageEvalDetail id="c1" />);
    expect(await screen.findByText(/Claude grading the image 1–5 on each trait/)).toBeInTheDocument();
    expect(screen.getAllByText("Hair is one outline")).toHaveLength(2);
    expect(screen.getByText("0.62 → 0.81")).toBeInTheDocument();
    expect(screen.getByText(/stash image-eval check c1/)).toBeInTheDocument();
    expect(screen.getByText("hair is built from small loops")).toBeInTheDocument();
    expect(screen.getByText(/12 imitations/)).toBeInTheDocument();
  });

  it("labels a call with the note", async () => {
    render(<ImageEvalDetail id="c1" />);
    await screen.findByText(/Claude grading the image 1–5 on each trait/);
    fireEvent.change(screen.getAllByLabelText("Note on this image")[1], { target: { value: "too thin" } });
    fireEvent.click(screen.getAllByText("I don't")[1]);
    await waitFor(() => expect(api.imageEvalLabelCall).toHaveBeenCalledWith("c1", "k1", "disliked", "too thin"));
  });
});

describe("call grades", () => {
  it("shows each trait's grade on an agent call", async () => {
    vi.mocked(api.imageEvalGet).mockResolvedValue(detail);
    vi.mocked(api.imageEvalExamples).mockResolvedValue([]);
    vi.mocked(api.imageEvalCalls).mockResolvedValue([{ ...call("k3", 0.69), comments: { summary: "Close", fixes: [], keep: [], traits: [{ trait: "line work", score: 4, why: "bold, slightly thin" }] } }]);
    render(<ImageEvalDetail id="c1" />);
    expect(await screen.findByText((_, el) => el?.textContent === "line work 4/5" && el.tagName === "SPAN")).toBeInTheDocument();
    expect(screen.getByText(/Claude grading the image 1–5 on each trait/)).toBeInTheDocument();
  });
});
