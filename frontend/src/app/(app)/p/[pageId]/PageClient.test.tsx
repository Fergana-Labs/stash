import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillPageView from "./PageClient";

const api = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
      this.name = "ApiError";
    }
  }

  return {
    ApiError,
    createCommentThread: vi.fn(),
    deleteCommentMessage: vi.fn(),
    deleteCommentThread: vi.fn(),
    getFolderContents: vi.fn(),
    getPage: vi.fn(),
    getPublicSkill: vi.fn(),
    listCommentThreads: vi.fn(),
    listObjectSkills: vi.fn(),
    reconcileCommentAnchors: vi.fn(),
    replyToCommentThread: vi.fn(),
    setCommentResolved: vi.fn(),
    trashItem: vi.fn(),
    updatePage: vi.fn(),
  };
});

const route = vi.hoisted(() => ({
  push: vi.fn(),
  search: "skill=private-skill",
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ workspaceId: "ws-1", pageId: "page-1" }),
  useRouter: () => ({ push: route.push }),
  useSearchParams: () => new URLSearchParams(route.search),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../../../../components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      name: "henry",
      display_name: "Henry",
      email: "henry@example.com",
      description: "",
      created_at: "2026-06-08T00:00:00Z",
      last_seen: "2026-06-08T00:00:00Z",
    },
    loading: false,
  }),
}));

vi.mock("../../../../lib/api", () => api);

vi.mock("../../../../skills/[slug]/SkillItemBodies", () => ({
  PageBody: () => <div>Skill page body</div>,
}));

vi.mock("../../../../components/DownloadMenu", () => ({
  downloadBlob: vi.fn(),
  downloadRenderedPdf: vi.fn(),
  htmlToPdfBlocks: vi.fn(),
  markdownToPdfBlocks: vi.fn(),
}));

vi.mock("../../../../components/SkeletonStates", () => ({
  DocumentPageSkeleton: () => <div>Loading page</div>,
}));

vi.mock("../../../../components/SkillIcons", () => ({
  SkillIcon: () => <span>Skill icon</span>,
}));

vi.mock("../../../../components/workspace/HtmlPageView", () => ({
  default: () => <div>HTML page view</div>,
  extractCommentIdsFromHtml: vi.fn(() => []),
}));

vi.mock("../../../../components/export/ExportDeckButton", () => ({
  default: () => <button>Export</button>,
}));

vi.mock("../../../../components/workspace/FileViewerHeader", () => ({
  default: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

vi.mock("../../../../components/workspace/MarkdownEditor", () => ({
  default: () => <div>Markdown editor</div>,
  extractCommentIdsFromMarkdown: vi.fn(() => []),
}));

vi.mock("../../../../components/workspace/CommentsSidebar", () => ({
  default: () => <aside>Comments</aside>,
}));

vi.mock("../../../../components/workspace/CommentComposerPopover", () => ({
  default: () => <div>Comment composer</div>,
}));

describe("SkillPageView access fallback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.search = "skill=private-skill";
    route.push.mockClear();
    api.getPage.mockRejectedValue(new api.ApiError(404, "Page not found"));
    api.getPublicSkill.mockRejectedValue(new Error("Skill not found"));
  });

  afterEach(() => {
    cleanup();
  });

  it("shows a full-screen access denied page when the linked Skill is not readable", async () => {
    render(<SkillPageView />);

    expect(
      await screen.findByRole("heading", {
        name: "You don't have access to this page",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/henry@example\.com/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to home" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.queryByText("Page not found")).not.toBeInTheDocument();
    expect(screen.queryByText("This page is not in a Skill yet.")).not.toBeInTheDocument();
  });
});
