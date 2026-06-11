import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Stash · One place your agents connect to all your data",
  description:
    "The one place your agents connect to all your data — GitHub, Drive, Gmail, Notion, Slack and more — plus an agent-native Drive in Markdown and HTML to write the work back into.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${instrumentSans.variable} ${jetbrainsMono.variable}`}>
      <head>
        <link
          href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap"
          rel="stylesheet"
        />
        <script
          dangerouslySetInnerHTML={{
            __html:
              "if(location.pathname==='/'&&location.hash){history.replaceState(null,'',location.pathname+location.search);window.scrollTo(0,0);}",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
