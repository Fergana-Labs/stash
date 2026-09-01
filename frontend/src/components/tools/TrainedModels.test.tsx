import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TrainedModels from "./TrainedModels";
import {
  checkModelCorpus,
  listFolders,
  listModelKinds,
  listTrainedModels,
  trainModel,
  type CorpusReport,
  type TrainedModel,
} from "@/lib/api";

vi.mock("sonner", () => ({
  toast: { error: vi.fn() },
}));

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }
  class PaymentRequiredError extends ApiError {
    checkoutUrl: string;
    constructor(message: string, checkoutUrl: string) {
      super(402, message);
      this.checkoutUrl = checkoutUrl;
    }
  }
  return {
    ApiError,
    PaymentRequiredError,
    listTrainedModels: vi.fn(),
    listModelKinds: vi.fn(),
    listFolders: vi.fn(),
    checkModelCorpus: vi.fn(),
    trainModel: vi.fn(),
    runModel: vi.fn(),
    getModelJob: vi.fn(),
    deleteTrainedModel: vi.fn(),
    createFolder: vi.fn(),
    createPage: vi.fn(),
  };
});

const READY: TrainedModel = {
  id: "m1",
  kind: "stylewriter",
  name: "me",
  status: "ready",
  words: 2140,
  base_model: "Qwen/Qwen2.5-14B-Instruct",
  corpus_folder_id: "f1",
  corpus: { usable_words: 2140, chunks: 9, sources: ["essay.md", "post.md"] },
  error: null,
  created_at: "2026-09-01T00:00:00Z",
  trained_at: "2026-09-01T00:06:00Z",
};

const REPORT: CorpusReport = {
  folder: { id: "f1", name: "Writing samples" },
  status: "ready",
  ready: true,
  documents: 2,
  usable_documents: 2,
  raw_words: 2300,
  usable_words: 2140,
  chunks: 9,
  duplicate_chunks: 0,
  duplicate_words: 0,
  minimum_words: 1000,
  recommended_words: 2000,
  reasons: [],
  warnings: [],
};

beforeEach(() => {
  vi.mocked(listModelKinds).mockResolvedValue([
    { kind: "stylewriter", title: "Stylewriter", base_model: "Qwen/Qwen2.5-14B-Instruct" },
  ]);
  vi.mocked(listFolders).mockResolvedValue({
    folders: [
      {
        id: "f1",
        owner_user_id: "u1",
        parent_folder_id: null,
        name: "Writing samples",
        created_by: "u1",
        created_at: "",
        updated_at: "",
      },
    ],
  } as never);
  vi.mocked(checkModelCorpus).mockResolvedValue(REPORT);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function pickFolderAndName() {
  await screen.findByText("Train a model");
  fireEvent.change(screen.getByLabelText("Model name"), { target: { value: "me" } });
  fireEvent.change(screen.getByLabelText("Corpus folder"), { target: { value: "f1" } });
  await waitFor(() => expect(checkModelCorpus).toHaveBeenCalledWith("stylewriter", "f1"));
  await screen.findByText(/2,140 usable words/);
}

describe("TrainedModels", () => {
  it("lists trained models with status and word count", async () => {
    vi.mocked(listTrainedModels).mockResolvedValue([READY]);
    render(<TrainedModels />);
    expect(await screen.findByText("me")).toBeTruthy();
    expect(screen.getByText("Ready")).toBeTruthy();
    expect(screen.getByText(/2,140 words from 2 pages/)).toBeTruthy();
  });

  it("checks the corpus when a folder is chosen and trains when ready", async () => {
    vi.mocked(listTrainedModels).mockResolvedValue([]);
    vi.mocked(trainModel).mockResolvedValue({ ...READY, status: "training" });
    render(<TrainedModels />);
    await pickFolderAndName();

    fireEvent.click(screen.getByRole("button", { name: "Train" }));
    await waitFor(() => expect(trainModel).toHaveBeenCalledWith("stylewriter", "me", "f1"));
    await waitFor(() => expect(listTrainedModels).toHaveBeenCalledTimes(2));
  });

  it("offers checkout when a training run must be paid for", async () => {
    vi.mocked(listTrainedModels).mockResolvedValue([]);
    const { PaymentRequiredError } = await import("@/lib/api");
    vi.mocked(trainModel).mockRejectedValue(
      new PaymentRequiredError("Training costs $20. Pay, then train again.", "https://pay.test/s")
    );
    render(<TrainedModels />);
    await pickFolderAndName();

    fireEvent.click(screen.getByRole("button", { name: "Train" }));
    const link = await screen.findByText("Pay and come back to train");
    expect(link.getAttribute("href")).toBe("https://pay.test/s");
    expect(screen.getByText(/Training costs \$20/)).toBeTruthy();
  });

  it("keeps Train disabled while the corpus is blocked", async () => {
    vi.mocked(listTrainedModels).mockResolvedValue([]);
    vi.mocked(checkModelCorpus).mockResolvedValue({
      ...REPORT,
      status: "blocked",
      ready: false,
      usable_words: 400,
      reasons: ["400 usable words; at least 1,000 are needed."],
    });
    render(<TrainedModels />);
    await screen.findByText("Train a model");
    fireEvent.change(screen.getByLabelText("Model name"), { target: { value: "me" } });
    fireEvent.change(screen.getByLabelText("Corpus folder"), { target: { value: "f1" } });
    await screen.findByText(/at least 1,000 are needed/);
    expect((screen.getByRole("button", { name: "Train" }) as HTMLButtonElement).disabled).toBe(
      true
    );
  });
});
