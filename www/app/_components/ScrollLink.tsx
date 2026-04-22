"use client";

import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";

type Props = AnchorHTMLAttributes<HTMLAnchorElement> & {
  to: string;
  children: ReactNode;
};

// Scrolls smoothly to an in-page anchor without pushing `#foo` into the URL,
// so refreshing or re-opening the tab doesn't auto-jump to the section.
export default function ScrollLink({ to, children, onClick, ...rest }: Props) {
  function handleClick(e: MouseEvent<HTMLAnchorElement>) {
    onClick?.(e);
    if (e.defaultPrevented) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const id = to.startsWith("#") ? to.slice(1) : to;
    const target = document.getElementById(id);
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <a href={to} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
}
