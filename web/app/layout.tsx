import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, DM_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

export const dynamic = 'force-dynamic'

const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  axes: ["opsz", "wdth"],
  variable: "--font-bricolage",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  axes: ["opsz"],
  variable: "--font-dm",
  display: "swap",
});

// The Companies terminal is monospaced end to end. Plex Mono for its 3270
// mainframe lineage, and because it shares nothing with the display face.
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Market Intelligence",
  description: "What moved markets today, why, and what to watch.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#EEEFF1" },
    { media: "(prefers-color-scheme: dark)", color: "#141519" },
  ],
};

// Runs before paint: picks stored theme, else system preference. Keeps first paint from flashing.
const themeInit = `
(function(){try{var s=localStorage.getItem('mi-theme');var d=window.matchMedia('(prefers-color-scheme: dark)').matches;
var t=(s==='light'||s==='dark')?s:(d?'dark':'light');document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${bricolage.variable} ${dmSans.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
