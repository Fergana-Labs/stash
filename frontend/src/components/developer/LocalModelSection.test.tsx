import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LocalModelSection from "./LocalModelSection";

const listWorkspaceAgentCredentials = vi.fn();
const connectWorkspaceLocalEndpoint = vi.fn();
const disconnectWorkspaceLocalEndpoint = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listWorkspaceAgentCredentials: (...args: unknown[]) => listWorkspaceAgentCredentials(...args),
    connectWorkspaceLocalEndpoint: (...args: unknown[]) => connectWorkspaceLocalEndpoint(...args),
    disconnectWorkspaceLocalEndpoint: (...args: unknown[]) =>
      disconnectWorkspaceLocalEndpoint(...args),
  };
});

describe("LocalModelSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listWorkspaceAgentCredentials.mockResolvedValue([]);
    connectWorkspaceLocalEndpoint.mockResolvedValue(["local"]);
    disconnectWorkspaceLocalEndpoint.mockResolvedValue([]);
  });

  it("renders the Local model section; Connect endpoint opens the URL/model/key form", async () => {
    render(<LocalModelSection />);
    await screen.findByText("Local model");
    expect(screen.getByRole("button", { name: "Connect endpoint" })).toBeDefined();
    // The form stays hidden until asked for.
    expect(screen.queryByPlaceholderText("http://your-host:11434/v1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Connect endpoint" }));
    expect(screen.getByPlaceholderText("http://your-host:11434/v1")).toBeDefined();
    expect(screen.getByPlaceholderText("llama3.1:8b")).toBeDefined();
    expect(screen.getByPlaceholderText("optional key…")).toBeDefined();
  });

  it("submits URL + model via connectWorkspaceLocalEndpoint, key omitted as null", async () => {
    render(<LocalModelSection />);
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

    expect(connectWorkspaceLocalEndpoint).toHaveBeenCalledWith(
      "http://my-host:11434/v1",
      "llama3.1:8b",
      null,
    );
  });

  it("shows Connected + Disconnect once the local endpoint is in the list", async () => {
    listWorkspaceAgentCredentials.mockResolvedValue(["local"]);
    render(<LocalModelSection />);
    await waitFor(() => expect(screen.getByText("Connected")).toBeDefined());

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(disconnectWorkspaceLocalEndpoint).toHaveBeenCalled();
  });
});
