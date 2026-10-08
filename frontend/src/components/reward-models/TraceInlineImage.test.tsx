import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AnchoredText from "./AnchoredText";
import TraceInlineImage from "./TraceInlineImage";
import { domSourceOffset } from "./source-anchors";

const fetchImage = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ fetchAuthed: fetchImage }));
const image = { id: "image-id", start: 0, end: 1, width: 120, height: 80 };
const revoke = vi.fn();

beforeEach(() => {
  fetchImage.mockResolvedValue({ ok: true, blob: async () => new Blob(["image"], { type: "image/png" }) });
  vi.stubGlobal("IntersectionObserver", class {
    constructor(private callback: (entries: { isIntersecting: boolean }[]) => void) {}
    observe() { this.callback([{ isIntersecting: true }]); }
    disconnect() {}
  });
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = () => "blob:trace-image";
    static revokeObjectURL = revoke;
  });
});
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

it("loads an authorized image, enlarges it, and releases its bytes on unmount", async () => {
  const view = render(<TraceInlineImage image={image} />);
  const preview = await screen.findByRole("img", { name: "Attached image" });
  expect(fetchImage).toHaveBeenCalledWith("/api/v1/rm/trace-images/image-id");
  expect(preview).toHaveAttribute("src", "blob:trace-image");
  fireEvent.click(screen.getByRole("button", { name: "Enlarge attached image" }));
  expect(screen.getByRole("dialog", { name: "Attached image" })).toBeVisible();
  expect(screen.getByRole("img", { name: "Full-size attached image" })).toBeVisible();
  view.unmount();
  expect(revoke).toHaveBeenCalledWith("blob:trace-image");
});

it("shows an unavailable placeholder when access is denied", async () => {
  fetchImage.mockResolvedValue({ ok: false });
  render(<TraceInlineImage image={image} />);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Image unavailable"));
  expect(screen.queryByRole("img")).toBeNull();
});

it("replaces attachment wrappers while preserving source offsets and quote highlights after the image", async () => {
  const wrapper = '<image name=[Image #1] path="/private/a.png">\n[input_image]\n</image>';
  const content = `Before 🐙\n${wrapper}\nPlease fix **this**.`;
  const start = content.indexOf(wrapper);
  const highlighted = content.indexOf("this");
  const { container } = render(<AnchoredText stepId="s1" content={content} markdown
    images={[{ ...image, start, end: start + wrapper.length }]}
    highlights={[{ id: "comment", start: highlighted, end: highlighted + 4, className: "highlight" }]}
    onSelectAnnotation={() => {}} />);
  await screen.findByRole("img", { name: "Attached image" });
  expect(container.textContent).not.toContain("/private/a.png");
  expect(container.textContent).not.toContain("[input_image]");
  for (const run of container.querySelectorAll<HTMLElement>("[data-o]")) {
    const offset = Number(run.dataset.o);
    expect(content.slice(offset, offset + run.textContent!.length)).toBe(run.textContent);
  }
  const mark = container.querySelector("mark[data-ids='comment']")!;
  expect(mark.textContent).toBe("this");
  expect(domSourceOffset(mark.firstChild!, 0)).toBe(highlighted);
});

it("explains an older missing image without displaying its raw local path", () => {
  const { container } = render(<AnchoredText stepId="old" content={'<image path="/private/shot.png">[input_image]</image>\nPlease fix this.'} markdown highlights={[]} onSelectAnnotation={() => {}} />);
  expect(container.textContent).toContain("Image wasn’t included in this recording");
  expect(container.textContent).not.toContain("/private/shot.png");
  expect(container.textContent).toContain("Please fix this.");
});

it("renders a recorded question reply as readable text with its original quote positions", () => {
  const content = '<send_user_message_question_reply>\n[{"answer":"No, use the classifier.","question":"Should we use a saved score?","questionItemId":"internal"}]\n</send_user_message_question_reply>';
  const { container } = render(<AnchoredText stepId="reply" content={content} markdown highlights={[]} onSelectAnnotation={() => {}} />);
  expect(container.textContent).toContain("No, use the classifier.");
  expect(container.textContent).not.toContain("questionItemId");
  for (const run of container.querySelectorAll<HTMLElement>("[data-o]")) {
    expect(content.slice(Number(run.dataset.o), Number(run.dataset.o) + run.textContent!.length)).toBe(run.textContent);
  }
});
