import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AgentUsagePanel from "./AgentUsagePanel";

it("copies the selected API example with the model and payload intact", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<AgentUsagePanel modelId="model-123" outputType="preference" sample={{ reply: "I'll help" }} />);
  fireEvent.click(screen.getByText("Connect"));
  fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
  fireEvent.click(screen.getByRole("button", { name: "Copy API example" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const curl = writeText.mock.calls[0][0] as string;
  expect(curl).toContain("/api/v1/intuitions/model-123/compare");
  expect(curl).toContain('"item_a"');
  expect(curl).toContain('"item_b"');
  expect(curl).toContain("I'\\''ll help");
  expect(curl.split("\n")[0]).toMatch(/ \\$/);

  fireEvent.click(screen.getByRole("tab", { name: "MCP" }));
  fireEvent.click(screen.getByRole("button", { name: "Copy API example" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
  expect(JSON.parse(writeText.mock.calls[1][0])).toEqual({
    tool: "stash_intuition_predict",
    arguments: { model_id: "model-123", item: JSON.stringify({ reply: "I'll help" }) },
  });
});
