import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CTI Detection Platform",
  description: "AI-driven CTI detection engineering platform"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
