import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { BreadcrumbProvider } from "../components/BreadcrumbContext";
import { ShareModalProvider } from "../lib/shareModalContext";
import StashShareModal from "../components/share/StashShareModal";

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Stash",
  description: "A shared memory for your AI agent team",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${instrumentSans.variable} ${jetbrainsMono.variable} ${spaceGrotesk.variable} antialiased min-h-screen`}
      >
        <BreadcrumbProvider>
          <ShareModalProvider>
            {children}
            <StashShareModal />
          </ShareModalProvider>
        </BreadcrumbProvider>
      </body>
    </html>
  );
}
