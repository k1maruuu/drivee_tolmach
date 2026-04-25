import type { Metadata } from "next";
import { JetBrains_Mono, Onest } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

const fontSans = Onest({
  variable: "--font-sans",
  subsets: ["latin", "cyrillic"],
});

const fontMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "Толмач",
  description: "Толмач — запросы на русском → SQL и визуализации",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ru"
      className={`${fontSans.variable} ${fontMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
