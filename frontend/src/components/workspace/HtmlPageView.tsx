"use client";

type Props = {
  html: string;
  title: string;
};

// HTML page renderer. The iframe sandbox is the entire defense — content
// gets a unique opaque origin, can't read parent cookies/storage, can't
// navigate the top frame. Scripts run, but in a vacuum, which is what
// makes AI-generated HTML safe to display.
export default function HtmlPageView({ html, title }: Props) {
  return (
    <iframe
      srcDoc={html}
      sandbox="allow-scripts"
      title={title}
      style={{
        width: "100%",
        aspectRatio: "16 / 9",
        border: 0,
        display: "block",
      }}
    />
  );
}
