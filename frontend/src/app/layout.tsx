import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { BreadcrumbProvider } from "../components/BreadcrumbContext";
import { ShellChromeProvider } from "../components/ShellChromeContext";
import { ShareModalProvider } from "../lib/shareModalContext";
import CartridgeShareModal from "../components/share/CartridgeShareModal";

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
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
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
          <ShellChromeProvider>
            <ShareModalProvider>
              {children}
              <CartridgeShareModal />
            </ShareModalProvider>
          </ShellChromeProvider>
        </BreadcrumbProvider>
      </body>
    </html>
  );
}
