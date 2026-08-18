type Props = { className?: string; size?: number };

const defaultSize = 18;

export function ClaudeCodeIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <path
        fill="#D97757"
        fillRule="evenodd"
        d="M21 10.95h3v3.1h-3v3.03h-1.49V20H18v-2.92h-1.49V20H15v-2.92H9V20H7.49v-2.92H6V20H4.49v-2.92H3v-3.03H0v-3.1h3V5h18v5.95ZM6 10.95h1.49V8.1H6v2.85Zm10.51 0H18V8.1h-1.49v2.85Z"
      />
    </svg>
  );
}

export function CodexIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <defs>
        <linearGradient id="codex-gradient" x1="12" x2="12" y1="3" y2="21" gradientUnits="userSpaceOnUse">
          <stop stopColor="#B1A7FF" />
          <stop offset=".5" stopColor="#7A9DFF" />
          <stop offset="1" stopColor="#3941FF" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="4.5" fill="white" />
      <path
        fill="url(#codex-gradient)"
        d="M9.06 3.34a4.58 4.58 0 0 1 4.96.97.1.1 0 0 0 .08.02 4.55 4.55 0 0 1 3.05.27 4.58 4.58 0 0 1 2.35 2.48c.21.51.31 1.04.31 1.6 0 .41-.04.82-.13 1.22a.12.12 0 0 0 .03.11 4.48 4.48 0 0 1 1.18 2.17 4.46 4.46 0 0 1-.89 3.86 4.55 4.55 0 0 1-2.33 1.55.12.12 0 0 0-.08.08 4.58 4.58 0 0 1-4.48 3.33 4.55 4.55 0 0 1-3.16-1.3.11.11 0 0 0-.1-.03 4.43 4.43 0 0 1-3.15-.33 4.54 4.54 0 0 1-1.61-1.34 4.69 4.69 0 0 1-.79-1.58 4.58 4.58 0 0 1-.01-2.3.12.12 0 0 0-.02-.1 4.47 4.47 0 0 1-1.04-1.65 4.56 4.56 0 0 1 1.82-5.41c.42-.28.91-.49 1.54-.68a.1.1 0 0 0 .07-.06 4.52 4.52 0 0 1 2.66-2.9Zm3.49 10.57a.64.64 0 0 0 0 1.27h3.63a.64.64 0 1 0 0-1.27h-3.63ZM8.46 9.23a.64.64 0 0 0-1.1.63l1.27 2.23-1.27 2.13a.64.64 0 1 0 1.1.65l1.45-2.46a.64.64 0 0 0 .01-.64L8.46 9.23Z"
      />
    </svg>
  );
}

export function CursorIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M22.11 5.68 12.5.14a1 1 0 0 0-1 0L1.89 5.68a.84.84 0 0 0-.42.73v11.18c0 .3.16.58.42.73l9.61 5.55a1 1 0 0 0 1 0l9.61-5.55a.84.84 0 0 0 .42-.73V6.41a.84.84 0 0 0-.42-.73Zm-.61 1.18-9.27 16.06c-.06.11-.23.06-.23-.06V12.34a.59.59 0 0 0-.3-.51L2.6 6.57c-.11-.06-.06-.23.06-.23h18.55c.26 0 .43.29.3.52Z" />
    </svg>
  );
}

export function OpenCodeIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M16 6H8v12h8V6Zm4 16H4V2h16v20Z" />
    </svg>
  );
}

export function GeminiCliIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <defs>
        <linearGradient id="gemini-cli-gradient" x1="24" x2="0" y1="6.59" y2="16.49" gradientUnits="userSpaceOnUse">
          <stop stopColor="#EE4D5D" />
          <stop offset=".33" stopColor="#B381DD" />
          <stop offset=".48" stopColor="#207CFE" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="4.39" fill="url(#gemini-cli-gradient)" />
      <path fill="#1E1E2E" d="m7.24 8.56 7.75 3.73-7.75 3.73v2.8l9.55-4.6v-3.86l-9.55-4.6v2.8Z" />
    </svg>
  );
}

export function OpenClawIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <defs>
        <linearGradient id="openclaw-gradient" x1="0" x2="24" y1="2" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF4D4D" />
          <stop offset="1" stopColor="#991B1B" />
        </linearGradient>
      </defs>
      <path fill="url(#openclaw-gradient)" d="M12 2.57c-6.33 0-9.5 5.27-9.5 9.49s3.17 8.44 6.33 9.5v2.1h2.11v-2.1s1.06.42 2.11 0v2.1h2.11v-2.1c3.17-1.06 6.33-5.28 6.33-9.5S18.33 2.57 12 2.57Z" />
      <path fill="url(#openclaw-gradient)" d="M3.56 9.95C.4 8.9-.66 11.01.4 13.12c1.05 2.11 3.16 1.05 4.22-1.06.63-1.47 0-2.1-1.06-2.1Zm16.88 0c3.16-1.05 4.22 1.06 3.16 3.17-1.05 2.11-3.16 1.05-4.22-1.06-.63-1.47 0-2.1 1.06-2.1Z" />
      <path fill="#FF4D4D" d="M5.51 1.88c.47-.29 1.03-.24 1.61.03.58.27 1.22.78 1.94 1.49a.32.32 0 0 1-.45.45 7.14 7.14 0 0 0-1.76-1.36c-.47-.23-.79-.21-1.02-.07a.32.32 0 0 1-.32-.54Zm11.37.03c.58-.27 1.14-.32 1.61-.03a.32.32 0 0 1-.32.54c-.23-.14-.55-.16-1.03.07-.47.22-1.06.67-1.75 1.36a.32.32 0 1 1-.45-.45c.72-.71 1.36-1.22 1.94-1.49Z" />
      <circle cx="8.84" cy="7.84" r="1.27" fill="#050810" />
      <circle cx="15.16" cy="7.84" r="1.27" fill="#050810" />
      <circle cx="9.05" cy="7.63" r=".53" fill="#00E5CC" />
      <circle cx="15.38" cy="7.63" r=".53" fill="#00E5CC" />
    </svg>
  );
}

export function HermesIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs>
        <linearGradient id="hermes-gold" x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="#F5C542" />
          <stop offset="1" stopColor="#D4961C" />
        </linearGradient>
      </defs>
      <rect x="30" y="10" width="4" height="46" rx="2" fill="url(#hermes-gold)" />
      <path d="M30 18c-6-4-16-4-20 0 4-2 12-2 18 2m2 2c-4-3-12-3-16 0 4-2 10-2 14 2" fill="none" stroke="#F5C542" strokeWidth="3" />
      <path d="M34 18c6-4 16-4 20 0-4-2-12-2-18 2m-2 2c4-3 12-3 16 0-4-2-10-2-14 2" fill="none" stroke="#D4961C" strokeWidth="3" />
      <path d="M32 48c-10-4-12-10-6-14-6 2-8 8-2 12-6-6-2-16 6-18M32 48c10-4 12-10 6-14 6 2 8 8 2 12 6-6 2-16-6-18" fill="none" stroke="url(#hermes-gold)" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="32" cy="10" r="4" fill="#F5C542" />
    </svg>
  );
}

export function ChromeIcon({ className, size = defaultSize }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 48 48" aria-hidden>
      <defs>
        <linearGradient id="chrome-red" x1="3.22" y1="15" x2="44.78" y2="15" gradientUnits="userSpaceOnUse">
          <stop stopColor="#D93025" />
          <stop offset="1" stopColor="#EA4335" />
        </linearGradient>
        <linearGradient id="chrome-yellow" x1="20.72" y1="47.68" x2="41.5" y2="11.68" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FCC934" />
          <stop offset="1" stopColor="#FBBC04" />
        </linearGradient>
        <linearGradient id="chrome-green" x1="26.6" y1="46.5" x2="5.82" y2="10.51" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1E8E3E" />
          <stop offset="1" stopColor="#34A853" />
        </linearGradient>
      </defs>
      <path fill="url(#chrome-red)" d="M24 12h20.78A24 24 0 0 0 3.22 12L13.61 30a12 12 0 0 1 10.4-18Z" />
      <path fill="url(#chrome-yellow)" d="M34.39 30 24 48a24 24 0 0 0 20.78-36H24a12 12 0 0 1 10.39 18Z" />
      <path fill="url(#chrome-green)" d="M13.61 30 3.22 12A24 24 0 0 0 24 48l10.39-18a12 12 0 0 1-20.78 0Z" />
      <circle cx="24" cy="24" r="10.5" fill="white" />
      <circle cx="24" cy="24" r="9.5" fill="#1A73E8" />
    </svg>
  );
}

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
      viewBox="0 0 256 193"
      aria-hidden
    >
      <path d="M58.18 192.05V93.14L27.5 65.08 0 49.5v127.34c0 8.84 7.16 16 16 16h42.18z" fill="#4285F4" />
      <path d="M197.82 192.05H240c8.84 0 16-7.16 16-16V49.5l-28.68 16.42-29.5 27.22v98.91z" fill="#34A853" />
      <path d="M58.18 93.14 53.9 54.8l4.28-37.3L128 69.87l69.82-52.37 4.67 35-4.67 40.64L128 145.5z" fill="#EA4335" />
      <path d="M197.82 17.5v75.64L256 49.5V25.32C256 5.57 233.45-6.2 216.73 6z" fill="#FBBC04" />
      <path d="M0 49.5 26.76 69.57l31.42 23.57V17.5L39.27 6C22.49-6.2 0 5.57 0 25.32z" fill="#C5221F" />
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

export function PostHogIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M3.2 14.6 5.6 10 4.7 5.4l4.6 1.4L12 3l2.7 3.8 4.6-1.4-.9 4.6 2.4 4.6-4.4 1.8L14.7 21 12 18.1 9.3 21l-1.7-4.6z"
        fill="#F54E00"
      />
      <circle cx="9.3" cy="11.7" r="1.1" fill="white" />
      <circle cx="14.7" cy="11.7" r="1.1" fill="white" />
      <path d="M9.2 15.1c1.8 1.2 3.8 1.2 5.6 0" stroke="white" strokeWidth="1.2" strokeLinecap="round" />
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

export function LinearIcon({ className, size = defaultSize }: Props) {
  // Official Linear mark — interlocking diagonals in Linear's indigo.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="#5E6AD2"
      aria-hidden
    >
      <path d="M2.886 4.18A11.982 11.982 0 0 1 11.99 0C18.624 0 24 5.376 24 12.009c0 3.64-1.62 6.903-4.18 9.105L2.887 4.18ZM1.181 6.561 17.44 22.82c-.336.176-.682.335-1.038.477L.703 7.6c.142-.356.3-.703.477-1.039h.001ZM.002 11.882 12.118 24c-.51-.025-1.014-.082-1.508-.17L.17 13.39a12.087 12.087 0 0 1-.17-1.508h.002Zm.452 4.341 7.323 7.324a12.03 12.03 0 0 1-7.323-7.324Z" />
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

export function XIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <path d="M13.9 10.47 22.04 1h-1.93l-7.07 8.23L7.4 1H.9l8.53 12.44L.9 23.37h1.93l7.46-8.68 5.96 8.68h6.5zm-2.64 3.07-.86-1.24L3.52 2.45h2.95l5.55 7.94.86 1.24 7.23 10.35h-2.95z" />
    </svg>
  );
}

export function InstagramIcon({ className, size = defaultSize }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="#FF0069"
      aria-hidden
    >
      <path d="M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077" />
    </svg>
  );
}

export function HeaviIcon({ className, size = defaultSize }: Props) {
  // Heavi mark — a bold H in the brand's dark slate.
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <rect x="1.5" y="1.5" width="21" height="21" rx="5" fill="#1E293B" />
      <path
        d="M8 6.5v11M16 6.5v11M8 12h8"
        stroke="#fff"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
