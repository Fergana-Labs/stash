export type NavigateOptions = {
  newTab?: boolean;
};

type LinkClickEvent = {
  metaKey: boolean;
  ctrlKey: boolean;
  button: number;
};

export function shouldOpenInNewTab(event: LinkClickEvent): boolean {
  return event.metaKey || event.ctrlKey || event.button === 1;
}

export function openInNewTab(href: string): void {
  window.open(href, "_blank", "noopener,noreferrer");
}
