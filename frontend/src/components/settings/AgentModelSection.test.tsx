import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AgentModelSection from "./AgentModelSection";

const listAgentCredentials = vi.fn();
const connectLocalEndpoint = vi.fn();
const disconnectAgentCredential = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listAgentCredentials: (...args: unknown[]) => listAgentCredentials(...args),
    connectLocalEndpoint: (...args: unknown[]) => connectLocalEndpoint(...args),
    disconnectAgentCredential: (...args: unknown[]) => disconnectAgentCredential(...args),
  };
});

describe("AgentModelSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listAgentCredentials.mockResolvedValue([]);
    connectLocalEndpoint.mockResolvedValue(["local"]);
    disconnectAgentCredential.mockResolvedValue([]);
  });

  it("renders four provider rows including Local model", async () => {
    render(<AgentModelSection />);
    await screen.findByText("Cloud agent model");
    expect(screen.getByText("Claude Code")).toBeDefined();
    expect(screen.getByText("Codex")).toBeDefined();
    expect(screen.getByText("OpenRouter")).toBeDefined();
    expect(screen.getByText("Local model")).toBeDefined();
    // The local row is the only endpoint row.
    expect(screen.getByRole("button", { name: "Connect endpoint" })).toBeDefined();
  });

  it("submits URL + model via connectLocalEndpoint, key omitted as null", async () => {
    render(<AgentModelSection />);
    await screen.findByText("Cloud agent model");

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
    await screen.findByText("Cloud agent model");

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
});
