import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WizardProvider } from "../wizard-ui";
import WebsiteEvalCard from "./WebsiteEvalCard";

const add = vi.hoisted(() => vi.fn());
vi.mock("@/lib/taste-api", () => ({ tasteGet: vi.fn(), tasteAddExamples: add }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

it("starts a website eval by asking for example sites it likes and doesn't, not past sessions", async () => {
  add.mockResolvedValue({ model_id: "eval-1", added: { liked: 2, disliked: 2 } });
  const send = vi.fn();
  const adoptModel = vi.fn();
  render(
    <WizardProvider value={{ modelId: null, send, refresh: vi.fn(), version: 0, busy: false, sessionId: "s1", adoptModel }}>
      <WebsiteEvalCard section="sources" />
    </WizardProvider>,
  );
  expect(screen.getByText("Show it example sites")).toBeTruthy();
  expect(screen.queryByText(/session/i)).toBeNull();
  const use = () => screen.getByRole("button", { name: /Use these 4 examples/ });
  fireEvent.change(screen.getByLabelText("Sites I like: paste URLs"), { target: { value: "https://linear.app\nhttps://vercel.com" } });
  fireEvent.change(screen.getByLabelText("Sites I don’t like: paste URLs"), { target: { value: "https://a.example\nnot a url\nhttps://b.example" } });
  fireEvent.click(use());
  await waitFor(() => expect(send).toHaveBeenCalledWith("Added 2 sites I like and 2 I don’t.", "event"));
  expect(add.mock.calls[0][0]).toBe("s1");
  expect(add.mock.calls[0][1].map((f: { url: string; label: string }) => [f.label, f.url])).toEqual([
    ["liked", "https://linear.app"], ["liked", "https://vercel.com"], ["disliked", "https://a.example"], ["disliked", "https://b.example"],
  ]);
  expect(adoptModel).toHaveBeenCalledWith("eval-1");
  expect(screen.getByText("Your example sites")).toBeTruthy();
});
