import type { Metadata } from "next";
import { Bebas_Neue, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const bebas = Bebas_Neue({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-bebas",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PerceptAI — Perception infrastructure for autonomous agents",
  description:
    "PerceptAI is the perception layer for AI agents. Real-time multimodal understanding, observability, and execution traces — built for production.",
  metadataBase: new URL("https://perceptai.dev"),
  openGraph: {
    title: "PerceptAI — Perception infrastructure for AI agents",
    description:
      "Real-time multimodal perception, observability, and execution traces for autonomous AI agents.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${bebas.variable} ${inter.variable} ${jetbrains.variable}`}
    >
      <body className="bg-background text-foreground font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
