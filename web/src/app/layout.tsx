import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Learnical",
  description: "The AI tutor that grades your steps, not just your answers.",
};

const navLinks = [
  { href: "/solve", label: "Tutor" },
  { href: "/topics", label: "Topics" },
  { href: "/practice", label: "Practice" },
  { href: "/scan", label: "Scan & Grade" },
  { href: "/progress", label: "Progress" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-white text-zinc-900">
        <header className="border-b border-zinc-200">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4">
            <Link href="/" className="text-lg font-bold text-emerald-600">
              Learnical
            </Link>
            <div className="flex gap-4 text-sm font-medium text-zinc-600">
              {navLinks.map((l) => (
                <Link key={l.href} href={l.href} className="hover:text-emerald-600">
                  {l.label}
                </Link>
              ))}
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">{children}</main>
        <footer className="border-t border-zinc-200 py-6 text-center text-xs text-zinc-400">
          Learnical — learn the method, not just the answer.
        </footer>
      </body>
    </html>
  );
}
