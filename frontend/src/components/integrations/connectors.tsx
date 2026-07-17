import type { ReactNode } from "react";

import type { IntegrationProvider } from "@/lib/integrations";

import {
  AsanaIcon,
  GmailIcon,
  GitHubIcon,
  GongIcon,
  GoogleDriveIcon,
  GranolaIcon,
  JiraIcon,
  LinearIcon,
  InstagramIcon,
  NotionIcon,
  PostHogIcon,
  SlackIcon,
  XIcon,
} from "./BrandIcons";

export type ConnectorKind =
  | "github"
  | "drive"
  | "notion"
  | "jira"
  | "asana"
  | "auto"
  | "extension";

export type Connector = {
  provider: IntegrationProvider;
  label: string;
  sourceType: string;
  kind: ConnectorKind;
  blurb: string;
  // Connecting auto-creates exactly one source (X) — there's nothing to "add",
  // so the page hides the add-source UI and browses that source directly.
  singleSource?: boolean;
};

export const CONNECTORS: Connector[] = [
  {
    provider: "github",
    label: "GitHub",
    sourceType: "github_repo",
    kind: "github",
    blurb: "Sync every repo you can see, or pick specific ones.",
  },
  {
    provider: "google",
    label: "Google Drive",
    sourceType: "google_drive",
    kind: "drive",
    blurb: "Index all of My Drive, or just one folder.",
  },
  {
    provider: "gmail",
    label: "Gmail",
    sourceType: "gmail",
    kind: "auto",
    blurb: "Search messages and read email on demand.",
  },
  {
    provider: "notion",
    label: "Notion",
    sourceType: "notion",
    kind: "notion",
    blurb: "Pick pages or databases shared with Skill.",
  },
  {
    provider: "jira",
    label: "Jira",
    sourceType: "jira_project",
    kind: "jira",
    blurb: "Search issues from a project.",
  },
  {
    provider: "asana",
    label: "Asana",
    sourceType: "asana_project",
    kind: "asana",
    blurb: "Navigate tasks from a project.",
  },
  {
    provider: "linear",
    label: "Linear",
    sourceType: "linear",
    kind: "auto",
    blurb: "Search and read your Linear issues.",
  },
  {
    provider: "slack",
    label: "Slack",
    sourceType: "slack",
    kind: "auto",
    blurb: "Channel history, kept in sync.",
  },
  {
    provider: "granola",
    label: "Granola",
    sourceType: "granola",
    kind: "auto",
    blurb: "Meeting notes and transcripts.",
  },
  // Gong is hidden until an OAuth app exists: no GONG_OAUTH_* creds are
  // registered anywhere (2026-07), so the card only ever showed users a
  // "not configured" error. Re-enable once the creds land in Render + .env.
  // {
  //   provider: "gong",
  //   label: "Gong",
  //   sourceType: "gong_calls",
  //   kind: "auto",
  //   blurb: "Call transcripts, kept in sync.",
  // },
  {
    provider: "posthog",
    label: "PostHog",
    sourceType: "posthog_project",
    kind: "auto",
    blurb: "Browse dashboards, insights, feature flags, and experiments.",
  },
  {
    provider: "x",
    label: "X",
    sourceType: "x_saves",
    kind: "auto",
    singleSource: true,
    blurb: "Connect X to sync your bookmarks, posts, and replies.",
  },
  {
    provider: "instagram",
    label: "Instagram",
    sourceType: "instagram_saves",
    kind: "extension",
    blurb: "Your Instagram saves, captured by the Stash browser extension.",
  },
];

// Maps a connected-source row's `type` back to the integration provider that
// owns it — used by the sidebar and the per-integration page routing.
export const providerForSourceType: Record<string, string> = {
  github_repo: "github",
  gmail: "gmail",
  google_drive: "google",
  google_drive_folder: "google",
  notion: "notion",
  jira_project: "jira",
  asana_project: "asana",
  linear: "linear",
  slack: "slack",
  granola: "granola",
  gong_calls: "gong",
  posthog_project: "posthog",
  x_saves: "x",
  instagram_saves: "instagram",
};

export function connectorForProvider(provider: string): Connector | undefined {
  return CONNECTORS.find((connector) => connector.provider === provider);
}

export function labelForProvider(provider: string): string {
  return connectorForProvider(provider)?.label ?? provider;
}

export function connectorIcon(provider: string): ReactNode {
  switch (provider) {
    case "github":
      return <GitHubIcon />;
    case "google":
      return <GoogleDriveIcon />;
    case "gmail":
      return <GmailIcon />;
    case "notion":
      return <NotionIcon />;
    case "jira":
      return <JiraIcon />;
    case "asana":
      return <AsanaIcon />;
    case "linear":
      return <LinearIcon />;
    case "slack":
      return <SlackIcon />;
    case "granola":
      return <GranolaIcon />;
    case "gong":
      return <GongIcon />;
    case "posthog":
      return <PostHogIcon />;
    case "x":
      return <XIcon />;
    case "instagram":
      return <InstagramIcon />;
    default:
      return null;
  }
}

export function labelForSourceType(type: string): string {
  if (type === "github_repo") return "GitHub";
  if (type === "gmail") return "Gmail";
  if (type === "google_drive") return "Google Drive";
  if (type === "google_drive_folder") return "Google Drive folder";
  if (type === "notion") return "Notion";
  if (type === "slack") return "Slack";
  if (type === "granola") return "Granola";
  if (type === "jira_project") return "Jira";
  if (type === "asana_project") return "Asana";
  if (type === "linear") return "Linear";
  if (type === "gong_calls") return "Gong";
  if (type === "posthog_project") return "PostHog";
  if (type === "x_saves") return "X saves";
  if (type === "instagram_saves") return "Instagram saves";
  return type;
}
