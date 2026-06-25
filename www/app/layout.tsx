import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Script from "next/script";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const title = "Stash · Give your agents a memory that compounds";
const description =
  "Stash connects your tools and captures every agent session into one context graph your agents — and your team — can read. Open source, MIT licensed, self-hostable.";

export const metadata: Metadata = {
  metadataBase: new URL("https://joinstash.ai"),
  title,
  description,
  openGraph: { title, description, type: "website", url: "https://joinstash.ai" },
  twitter: { card: "summary_large_image", title, description },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${instrumentSans.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable}`}
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "if(location.pathname==='/'&&location.hash){history.replaceState(null,'',location.pathname+location.search);window.scrollTo(0,0);}",
          }}
        />
      </head>
      <body>
        {children}
        {/* X (Twitter) conversion tracking base code — pixel id rcxyy */}
        <Script id="x-pixel" strategy="afterInteractive">
          {`!function(e,t,n,s,u,a){e.twq||(s=e.twq=function(){s.exe?s.exe.apply(s,arguments):s.queue.push(arguments);
},s.version='1.1',s.queue=[],u=t.createElement(n),u.async=!0,u.src='https://static.ads-twitter.com/uwt.js',
a=t.getElementsByTagName(n)[0],a.parentNode.insertBefore(u,a))}(window,document,'script');
twq('config','rcxyy');`}
        </Script>
      </body>
    </html>
  );
}
