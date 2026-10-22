import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImageEvalCard from "./ImageEvalCard";
import { WizardProvider } from "../wizard-ui";
import * as api from "@/lib/image-eval-api";

vi.mock("@/lib/image-eval-api", async (original) => ({
  ...(await original<typeof import("@/lib/image-eval-api")>()),
  imageEvalGet: vi.fn(), imageEvalUploadExamples: vi.fn(), imageEvalExamples: vi.fn(), imageEvalInterview: vi.fn(), imageEvalAnswer: vi.fn(),
}));
vi.mock("@/components/image-eval/ImageEvalImage", () => ({ default: ({ alt }: { alt: string }) => <span>{alt}</span> }));

const detail = (liked: number) => ({
  id: "e1", model_id: "m1", name: "Yoko", description: "", style_brief: "", interview: null as null | api.ImageEvalInterview, build: null, trained: false, trained_at: null,
  heldout_accuracy: null, heldout_balanced_accuracy: null, heldout_method: null, liked: null, disliked: null,
  created_at: "2026-10-22T06:00:00Z", updated_at: "2026-10-22T06:00:00Z",
  examples: { liked, disliked: 0, imitations: 0 }, calls: 0, needs_training: true,
});

describe("ImageEvalCard examples", () => {
  beforeEach(() => {
    globalThis.URL.createObjectURL = vi.fn(() => "blob:x");
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  it("shows thumbnails and progress while uploading, then builds with only liked images", async () => {
    vi.mocked(api.imageEvalGet).mockResolvedValueOnce(detail(0)).mockResolvedValue(detail(12));
    const waiting: (() => void)[] = [];
    vi.mocked(api.imageEvalUploadExamples).mockImplementation(() => new Promise((resolve) => { waiting.push(() => resolve([])); }));
    const send = vi.fn();
    const { container } = render(<WizardProvider value={{ modelId: "m1", send, refresh: () => {}, version: 0, busy: false }}><ImageEvalCard section="examples" evalId="e1" /></WizardProvider>);

    expect(await screen.findByText("Show it the style")).toBeInTheDocument();
    expect(screen.queryByLabelText(/aren't the style/)).not.toBeInTheDocument();
    const files = Array.from({ length: 12 }, (_, i) => new File(["x"], `d${i}.png`, { type: "image/png" }));
    fireEvent.change(screen.getByLabelText("Images in the style"), { target: { files } });

    expect(await screen.findByRole("progressbar", { name: "Uploading images" })).toBeInTheDocument();
    expect(container.querySelectorAll("img")).toHaveLength(12);
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    // 12 images go up as batches of 10 and 2.
    await act(async () => { while (waiting.length) { waiting.shift()!(); await Promise.resolve(); } });

    const build = await screen.findByRole("button", { name: "Continue" });
    await waitFor(() => expect(build).toBeEnabled());
    fireEvent.click(build);
    expect(send).toHaveBeenCalledWith("I added 12 images in the style.", "event");
  });
});

describe("ImageEvalCard progress", () => {
  it("walks the steps, shows what it noticed and each near-miss as it is drawn", async () => {
    vi.mocked(api.imageEvalGet).mockResolvedValue({
      ...detail(34), style_brief: "- **Line:** wobbly near-black crayon",
      build: { stage: "imitations", done: 2, total: 12, started_at: Date.now() / 1000 - 75 },
    });
    vi.mocked(api.imageEvalExamples).mockResolvedValue([
      { id: "i1", label: "disliked", source: "imitation", call_id: null, filename: "a cat in a box", note: "", heldout_score: null, created_at: "" },
      { id: "i2", label: "disliked", source: "imitation", call_id: null, filename: "a mug", note: "", heldout_score: null, created_at: "" },
    ]);
    render(<WizardProvider value={{ modelId: "m1", send: vi.fn(), refresh: () => {}, version: 0, busy: false }}><ImageEvalCard section="progress" evalId="e1" /></WizardProvider>);

    expect(await screen.findByText("Drawing near-misses · 2/12")).toBeInTheDocument();
    expect(screen.getByText(/^1:1\d · usually 4–5 minutes/)).toBeInTheDocument();
    expect(screen.getByLabelText("done")).toBeInTheDocument();
    expect(screen.getByLabelText("in progress")).toBeInTheDocument();
    expect(screen.getByText("wobbly near-black crayon")).toBeInTheDocument();
    expect(await screen.findByText("Near-miss: a cat in a box")).toBeInTheDocument();
    expect(screen.getByText("Near-miss: a mug")).toBeInTheDocument();
  });
});

describe("ImageEvalCard questions", () => {
  it("asks what only the person knows, then sends their answers and the images to leave out", async () => {
    vi.mocked(api.imageEvalGet).mockResolvedValue(detail(34));
    vi.mocked(api.imageEvalInterview).mockResolvedValue({
      questions: [
        { question: "Is the offset tan fill essential?", why: "decides color fixes", options: ["Essential", "Incidental"] },
        { question: "What do imitators get wrong?", why: "", options: ["Line weight", "Faces"] },
      ],
      outliers: ["x9"], answers: [], left_out: [], done: false,
    });
    vi.mocked(api.imageEvalAnswer).mockResolvedValue(detail(33));
    const send = vi.fn();
    render(<WizardProvider value={{ modelId: "m1", send, refresh: () => {}, version: 0, busy: false }}><ImageEvalCard section="questions" evalId="e1" /></WizardProvider>);

    expect(await screen.findByText("A few questions only you can answer")).toBeInTheDocument();
    const build = screen.getByRole("button", { name: "Build it" });
    expect(build).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Essential" }));
    fireEvent.change(screen.getByLabelText("Your answer: What do imitators get wrong?"), { target: { value: "They draw hair as one outline" } });
    fireEvent.click(screen.getByRole("button", { name: "Keep; tap to leave out" }));
    fireEvent.click(build);

    await waitFor(() => expect(send).toHaveBeenCalledWith("I answered 2 questions and left out 1 image.", "event"));
    expect(api.imageEvalAnswer).toHaveBeenCalledWith("e1", {
      answers: [
        { question: "Is the offset tan fill essential?", answer: "Essential" },
        { question: "What do imitators get wrong?", answer: "They draw hair as one outline" },
      ],
      leave_out: ["x9"], skipped: false,
    });
  });
});
