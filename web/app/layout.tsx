import type { Metadata } from "next";
import "./globals.css";

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: "Market Intelligence Engine",
  description: "Internal use only",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" style={{ height: '100%' }}>
      <body style={{ height: '100%' }}>{children}</body>
    </html>
  );
}
