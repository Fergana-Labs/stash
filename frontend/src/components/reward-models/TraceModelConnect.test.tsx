import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import TraceModelConnect from "./TraceModelConnect";

it("copies a trace scoring request for the selected trace and model", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const { rerender } = render(<TraceModelConnect modelId="custom" traceId="trace-one" />);
  fireEvent.click(screen.getByText("Connect"));
  fireEvent.click(screen.getByRole("button", { name: "Copy API example" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  expect(writeText.mock.calls[0][0]).toContain("/api/v1/rm/traces/trace-one/score");
  expect(writeText.mock.calls[0][0]).toContain('"reward_model_id": "custom"');
  expect(writeText.mock.calls[0][0].split("\n")[0]).toMatch(/ \\$/);
  rerender(<TraceModelConnect modelId="custom" traceId="trace-two" />);
  expect(screen.queryByText("Copied")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copy API example" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
  expect(writeText.mock.calls[1][0]).toContain("/api/v1/rm/traces/trace-two/score");
});
