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
    // Key and size fields left empty → null.
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(connectLocalEndpoint).toHaveBeenCalledWith(
      "http://my-host:11434/v1",
      "llama3.1:8b",
      null,
      null,
      null,
    );
  });

  it("submits custom sizes via connectLocalEndpoint", async () => {
    render(<AgentModelSection />);
    await screen.findByText("Cloud agent model");

    fireEvent.click(screen.getByRole("button", { name: "Connect endpoint" }));
    fireEvent.change(screen.getByPlaceholderText("http://your-host:11434/v1"), {
      target: { value: "http://my-host:11434/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("llama3.1:8b"), {
      target: { value: "llama3.1:8b" },
    });
    fireEvent.change(screen.getByLabelText("Context window"), { target: { value: "32768" } });
    fireEvent.change(screen.getByLabelText("Max output tokens"), { target: { value: "4096" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(connectLocalEndpoint).toHaveBeenCalledWith(
      "http://my-host:11434/v1",
      "llama3.1:8b",
      null,
      32768,
      4096,
    );
  });

  it("disables Connect when a filled size field is not a positive integer", async () => {
    render(<AgentModelSection />);
    await screen.findByText("Cloud agent model");

    fireEvent.click(screen.getByRole("button", { name: "Connect endpoint" }));
    fireEvent.change(screen.getByPlaceholderText("http://your-host:11434/v1"), {
      target: { value: "http://my-host:11434/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("llama3.1:8b"), {
      target: { value: "llama3.1:8b" },
    });
    fireEvent.change(screen.getByLabelText("Context window"), { target: { value: "0" } });

    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
  });

  it("surfaces the documented size defaults in the form help text", async () => {
    render(<AgentModelSection />);
    await screen.findByText("Cloud agent model");

    fireEvent.click(screen.getByRole("button", { name: "Connect endpoint" }));
    const help = await screen.findByText(/Leave blank for the documented defaults/);
    expect(help.textContent).toContain("131072");
    expect(help.textContent).toContain("8192");
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
