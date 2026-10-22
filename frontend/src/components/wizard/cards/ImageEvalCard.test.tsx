import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImageEvalCard from "./ImageEvalCard";
import { WizardProvider } from "../wizard-ui";
import * as api from "@/lib/image-eval-api";

vi.mock("@/lib/image-eval-api", async (original) => ({
  ...(await original<typeof import("@/lib/image-eval-api")>()),
  imageEvalGet: vi.fn(), imageEvalUploadExamples: vi.fn(),
}));

const detail = (liked: number) => ({
  id: "e1", model_id: "m1", name: "Yoko", description: "", style_brief: "", build: null, trained: false, trained_at: null,
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
    expect(screen.getByRole("button", { name: "Build it" })).toBeDisabled();
    // 12 images go up as batches of 10 and 2.
    await act(async () => { while (waiting.length) { waiting.shift()!(); await Promise.resolve(); } });

    const build = await screen.findByRole("button", { name: "Build it" });
    await waitFor(() => expect(build).toBeEnabled());
    fireEvent.click(build);
    expect(send).toHaveBeenCalledWith("I added 12 images in the style.", "event");
  });
});
