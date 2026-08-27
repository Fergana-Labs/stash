import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AgentModelSection from "./AgentModelSection";

const listAgentCredentials = vi.fn();
const connectLocalEndpoint = vi.fn();
const disconnectAgentCredential = vi.fn();
const getLocalModelsJson = vi.fn();
const saveLocalModelsJson = vi.fn();
const resetLocalModelsJson = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listAgentCredentials: (...args: unknown[]) => listAgentCredentials(...args),
    connectLocalEndpoint: (...args: unknown[]) => connectLocalEndpoint(...args),
    disconnectAgentCredential: (...args: unknown[]) => disconnectAgentCredential(...args),
    getLocalModelsJson: (...args: unknown[]) => getLocalModelsJson(...args),
    saveLocalModelsJson: (...args: unknown[]) => saveLocalModelsJson(...args),
    resetLocalModelsJson: (...args: unknown[]) => resetLocalModelsJson(...args),
  };
});

const DEFAULT_MODELS_JSON = `{
  "providers": {
    "local": {
      "baseUrl": "http://tunnel.example/v1",
      "api": "openai-completions",
      "apiKey": "$STASH_LOCAL_KEY"
    }
  }
}`;

const CUSTOM_MODELS_JSON = `{
  "providers": {
    "local": {
      "baseUrl": "http://tunnel.example/v1",
      "api": "openai-completions",
      "apiKey": "$STASH_LOCAL_KEY",
      "models": [{"id": "extra", "contextWindow": 65536, "maxTokens": 4096}]
    }
  }
}`;

describe("AgentModelSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listAgentCredentials.mockResolvedValue([]);
    connectLocalEndpoint.mockResolvedValue(["local"]);
    disconnectAgentCredential.mockResolvedValue([]);
    getLocalModelsJson.mockResolvedValue({ models_json: DEFAULT_MODELS_JSON, stored: false });
    saveLocalModelsJson.mockResolvedValue({ ok: true, stored: true });
    resetLocalModelsJson.mockResolvedValue({ ok: true, stored: false });
  });

  function connectLocal(): void {
    // The local row shows its connected branch (Disconnect + Edit models.json).
    listAgentCredentials.mockResolvedValueOnce(["local"]);
  }

  it("renders four provider rows including Local model", async () => {
    render(<AgentModelSection />);
    // Gate on the row label (renders in the same commit as its buttons),
    // not the section heading, which renders before the credential fetch.
    await screen.findByText("Local model");
    expect(screen.getByText("Claude Code")).toBeDefined();
    expect(screen.getByText("Codex")).toBeDefined();
    expect(screen.getByText("OpenRouter")).toBeDefined();
    expect(screen.getByText("Local model")).toBeDefined();
    // The local row is the only endpoint row.
    expect(screen.getByRole("button", { name: "Connect endpoint" })).toBeDefined();
  });

  it("submits URL + model via connectLocalEndpoint, key omitted as null", async () => {
    render(<AgentModelSection />);
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Connect endpoint" }));
    fireEvent.change(screen.getByPlaceholderText("http://your-host:11434/v1"), {
      target: { value: "http://my-host:11434/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("llama3.1:8b"), {
      target: { value: "llama3.1:8b" },
    });
    // Key left empty.
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(connectLocalEndpoint).toHaveBeenCalledWith("http://my-host:11434/v1", "llama3.1:8b", null);
  });

  it("shows Connected + Disconnect once the local endpoint is in the list", async () => {
    render(<AgentModelSection />);
    // Wait for the fetched row (same commit as its Connect endpoint button),
    // not the pre-fetch heading.
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Connect endpoint" }));
    fireEvent.change(screen.getByPlaceholderText("http://your-host:11434/v1"), {
      target: { value: "http://my-host:11434/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("llama3.1:8b"), {
      target: { value: "qwen2:7b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(screen.getByText("Connected")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(disconnectAgentCredential).toHaveBeenCalledWith("local");
  });

  it("shows Edit models.json only on the connected local row", async () => {
    connectLocal();
    render(<AgentModelSection />);
    await screen.findByText("Local model");
    await waitFor(() => expect(screen.getByText("Connected")).toBeDefined());
    // Exactly one editor affordance — on the local row; the other three
    // (unconnected) rows have none.
    expect(screen.getAllByRole("button", { name: "Edit models.json" })).toHaveLength(1);
  });

  it("loads the effective models.json on open with a Default indicator", async () => {
    connectLocal();
    render(<AgentModelSection />);
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Edit models.json" }));

    const textarea = await screen.findByRole("textbox", { name: "models.json" });
    await waitFor(() => expect(textarea).toHaveValue(DEFAULT_MODELS_JSON));
    expect(getLocalModelsJson).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Default")).toBeDefined();
    expect(screen.queryByText("Custom")).toBeNull();
  });

  it("shows a Custom indicator for a stored override", async () => {
    connectLocal();
    getLocalModelsJson.mockResolvedValue({ models_json: CUSTOM_MODELS_JSON, stored: true });
    render(<AgentModelSection />);
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Edit models.json" }));

    const textarea = await screen.findByRole("textbox", { name: "models.json" });
    await waitFor(() => expect(textarea).toHaveValue(CUSTOM_MODELS_JSON));
    expect(screen.getByText("Custom")).toBeDefined();
  });

  it("save submits the textarea text verbatim", async () => {
    connectLocal();
    render(<AgentModelSection />);
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Edit models.json" }));
    const textarea = await screen.findByRole("textbox", { name: "models.json" });
    await waitFor(() => expect(textarea).toHaveValue(DEFAULT_MODELS_JSON));

    fireEvent.change(textarea, { target: { value: CUSTOM_MODELS_JSON } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(saveLocalModelsJson).toHaveBeenCalledTimes(1));
    expect(saveLocalModelsJson).toHaveBeenCalledWith(CUSTOM_MODELS_JSON);
    expect(saveLocalModelsJson).toHaveBeenLastCalledWith(CUSTOM_MODELS_JSON);
    expect(screen.queryByText(/error/i)).toBeNull();
  });

  it("shows the parse error on bad save and keeps the user's text", async () => {
    connectLocal();
    render(<AgentModelSection />);
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Edit models.json" }));
    const textarea = await screen.findByRole("textbox", { name: "models.json" });
    await waitFor(() => expect(textarea).toHaveValue(DEFAULT_MODELS_JSON));

    const userText = '{"providers": {';
    fireEvent.change(textarea, { target: { value: userText } });
    saveLocalModelsJson.mockRejectedValueOnce(
      new Error("models.json is not valid JSON: Expecting value: line 1 column 1 (char 0)"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText(
      "models.json is not valid JSON: Expecting value: line 1 column 1 (char 0)",
    );
    // The user's text stays in the editor — last-good server value untouched,
    // and no re-fetch happened after the failed save.
    expect(textarea).toHaveValue(userText);
    expect(getLocalModelsJson).toHaveBeenCalledTimes(1);
  });

  it("reset deletes the override and reloads the default", async () => {
    connectLocal();
    // Open with the stored override, then the reset re-fetch returns the default.
    getLocalModelsJson
      .mockResolvedValueOnce({ models_json: CUSTOM_MODELS_JSON, stored: true })
      .mockResolvedValueOnce({ models_json: DEFAULT_MODELS_JSON, stored: false });
    render(<AgentModelSection />);
    await screen.findByText("Local model");

    fireEvent.click(screen.getByRole("button", { name: "Edit models.json" }));
    const textarea = await screen.findByRole("textbox", { name: "models.json" });
    await waitFor(() => expect(textarea).toHaveValue(CUSTOM_MODELS_JSON));
    expect(screen.getByText("Custom")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Reset to default" }));

    await waitFor(() => expect(resetLocalModelsJson).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(textarea).toHaveValue(DEFAULT_MODELS_JSON));
    expect(screen.getByText("Default")).toBeDefined();
  });
});
