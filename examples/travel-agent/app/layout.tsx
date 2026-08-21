import "./globals.css";

export const metadata = {
  title: "Atlas — travel planning",
  description: "The planning assistant inside your booking tool.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
