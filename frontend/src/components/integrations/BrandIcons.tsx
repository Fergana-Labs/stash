type Props = { className?: string; size?: number };

const defaultSize = 18;

export function GitHubIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.71.08-.71 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.04 0 0 .97-.31 3.18 1.18a11 11 0 0 1 2.89-.39c.98 0 1.97.13 2.89.39 2.21-1.49 3.18-1.18 3.18-1.18.63 1.58.23 2.75.11 3.04.74.81 1.19 1.84 1.19 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z" />
    </svg>
  );
}

export function GoogleDriveIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 87.3 78"
      aria-hidden
    >
      <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da" />
      <path d="m43.65 25 -13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0-1.2 4.5h27.5z" fill="#00ac47" />
      <path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.5l5.85 11.5z" fill="#ea4335" />
      <path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d" />
      <path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc" />
      <path d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00" />
    </svg>
  );
}

export function GmailIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
    >
      <path d="M3.2 5.2h17.6c.7 0 1.2.5 1.2 1.2v11.2c0 .7-.5 1.2-1.2 1.2H3.2c-.7 0-1.2-.5-1.2-1.2V6.4c0-.7.5-1.2 1.2-1.2z" fill="#fff" />
      <path d="M4 7.7v9.1h2.6V9.6L12 13.7l5.4-4.1v7.2H20V7.7l-8 6.1z" fill="#EA4335" />
      <path d="M4 7.7 12 13.8l8-6.1V6.4L12 12.5 4 6.4z" fill="#FBBC04" />
      <path d="M2 6.4v11.2c0 .7.5 1.2 1.2 1.2H4V7.7z" fill="#4285F4" />
      <path d="M20 7.7v11.1h.8c.7 0 1.2-.5 1.2-1.2V6.4z" fill="#34A853" />
    </svg>
  );
}

export function ObsidianIcon({ className, size = defaultSize }: Props) {
  // Renders the official Obsidian logo SVG asset from /public.
  // Tip: use plain <img> here — next/image's optimizer would re-encode
  // away the gradients and look worse.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/obsidian-logo.svg"
      alt=""
      width={size}
      height={size}
      className={className}
      aria-hidden
    />
  );
}

export function GranolaIcon({ className, size = defaultSize }: Props) {
  // Official Granola app icon from /public (PNG, so use plain <img>).
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/granola-logo.png"
      alt=""
      width={size}
      height={size}
      className={className}
      aria-hidden
    />
  );
}

export function NotionIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.139c-.093-.514.28-.887.747-.933z" />
    </svg>
  );
}

export function SnowflakeIcon({ className, size = defaultSize }: Props) {
  // Snowflake mark — a six-spoke flake in Snowflake blue.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      stroke="#29B5E8"
      strokeWidth="1.6"
      strokeLinecap="round"
      fill="none"
      aria-hidden
    >
      <g>
        <line x1="12" y1="3" x2="12" y2="21" />
        <line x1="4.2" y1="7.5" x2="19.8" y2="16.5" />
        <line x1="4.2" y1="16.5" x2="19.8" y2="7.5" />
        <path d="M12 6.4l-1.8-1.8M12 6.4l1.8-1.8M12 17.6l-1.8 1.8M12 17.6l1.8 1.8" />
        <path d="M6.6 9.5l-2.5.1M6.6 9.5l-.7-2.4M17.4 14.5l2.5-.1M17.4 14.5l.7 2.4" />
        <path d="M6.6 14.5l-.7 2.4M6.6 14.5l-2.5-.1M17.4 9.5l.7-2.4M17.4 9.5l2.5.1" />
      </g>
    </svg>
  );
}

export function GongIcon({ className, size = defaultSize }: Props) {
  // Gong mark — a purple ring with a centered dot.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9.2" stroke="#8039DF" strokeWidth="2.2" />
      <circle cx="12" cy="12" r="3.4" fill="#8039DF" />
    </svg>
  );
}

export function JiraIcon({ className, size = defaultSize }: Props) {
  // Official Jira mark — interlocking chevrons in Jira blue.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="#2684FF"
      aria-hidden
    >
      <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0z" />
    </svg>
  );
}

export function AsanaIcon({ className, size = defaultSize }: Props) {
  // Official Asana mark — three coral dots forming a triangle.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="#F06A6A"
      aria-hidden
    >
      <circle cx="12" cy="16.4" r="4.6" />
      <circle cx="6.4" cy="7.3" r="4.6" />
      <circle cx="17.6" cy="7.3" r="4.6" />
    </svg>
  );
}

export function SlackIcon({ className, size = defaultSize }: Props) {
  // Official Slack mark — four rounded shapes in Slack's brand colors.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 122.8 122.8"
      aria-hidden
    >
      <path d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9zm6.5 0c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9z" fill="#E01E5A" />
      <path d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9zm0 6.5c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58.1 0 52.3 0 45.2s5.8-12.9 12.9-12.9z" fill="#36C5F0" />
      <path d="M97 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97zm-6.5 0c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.7 5.8 70.5 0 77.6 0s12.9 5.8 12.9 12.9z" fill="#2EB67D" />
      <path d="M77.6 97c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97zm0-6.5c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9z" fill="#ECB22E" />
    </svg>
  );
}
