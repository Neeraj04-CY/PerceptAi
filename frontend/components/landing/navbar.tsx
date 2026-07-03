"use client";

import { useEffect, useState, type MouseEvent } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const nav = [
  { label: "Product", href: "#features" },
  { label: "Compare", href: "#compare" },
  { label: "Pricing", href: "#pricing" },
  { label: "Dashboard", href: "/dashboard" },
];

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  const handleNavClick = (
    event: MouseEvent<HTMLAnchorElement>,
    href: string
  ) => {
    if (!href.startsWith("#")) return;
    event.preventDefault();
    document.querySelector(href)?.scrollIntoView({ behavior: "smooth" });
    setOpen(false);
  };

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "fixed top-0 inset-x-0 z-50 transition-all duration-500",
        scrolled ? "py-3" : "py-5"
      )}
      data-testid="navbar"
    >
      <div className="mx-auto max-w-container px-6">
        <div
          className={cn(
            "flex items-center justify-between rounded-full px-4 py-2 transition-all duration-500",
            scrolled
              ? "border border-white/10 bg-black/40 backdrop-blur-xl"
              : "border border-transparent"
          )}
        >
          <a
            href="/"
            className="flex items-center gap-2 pl-2"
            data-testid="navbar-logo"
          >
            <Logo />
            <span className="font-display tracking-[0.12em] text-lg text-white">
              PERCEPT<span className="text-accent">AI</span>
            </span>
          </a>

          <nav className="hidden md:flex items-center gap-1">
            {nav.map((item) =>
              item.href.startsWith("#") ? (
                <a
                  key={item.label}
                  href={item.href}
                  onClick={(event) => handleNavClick(event, item.href)}
                  data-testid={`nav-link-${item.label.toLowerCase()}`}
                  className="px-4 py-2 text-sm text-white/60 hover:text-white transition-colors duration-300"
                >
                  {item.label}
                </a>
              ) : (
                <Link
                  key={item.label}
                  href={item.href}
                  data-testid={`nav-link-${item.label.toLowerCase()}`}
                  className="px-4 py-2 text-sm text-white/60 hover:text-white transition-colors duration-300"
                >
                  {item.label}
                </Link>
              )
            )}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              data-testid="nav-signin-btn"
              className="text-white/70"
              asChild
            >
              <Link href="/signin">Sign in</Link>
            </Button>
            <Button
              variant="primary"
              size="sm"
              data-testid="nav-cta-btn"
              className="font-medium"
              asChild
            >
              <Link href="/signup">Start building</Link>
            </Button>
          </div>

          <button
            onClick={() => setOpen((v) => !v)}
            className="md:hidden rounded-full p-2 text-white/80 hover:bg-white/5"
            aria-label="Toggle menu"
            data-testid="nav-mobile-toggle"
          >
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>

        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="md:hidden mt-2 rounded-2xl border border-white/10 bg-black/70 backdrop-blur-xl p-4"
              data-testid="nav-mobile-menu"
            >
              <div className="flex flex-col gap-1">
                {nav.map((item) =>
                  item.href.startsWith("#") ? (
                    <a
                      key={item.label}
                      href={item.href}
                      onClick={(event) => handleNavClick(event, item.href)}
                      className="px-3 py-3 text-sm text-white/70 hover:text-white border-b border-white/5 last:border-0"
                    >
                      {item.label}
                    </a>
                  ) : (
                    <Link
                      key={item.label}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className="px-3 py-3 text-sm text-white/70 hover:text-white border-b border-white/5 last:border-0"
                    >
                      {item.label}
                    </Link>
                  )
                )}
                <div className="flex gap-2 pt-3">
                  <Button variant="secondary" size="sm" className="flex-1" asChild>
                    <Link href="/signin" onClick={() => setOpen(false)}>
                      Sign in
                    </Link>
                  </Button>
                  <Button variant="primary" size="sm" className="flex-1" asChild>
                    <Link href="/signup" onClick={() => setOpen(false)}>
                      Start
                    </Link>
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.header>
  );
}

function Logo() {
  return (
    <div className="relative h-8 w-8">
      <div className="absolute inset-0 rounded-md border border-accent/40" />
      <div className="absolute inset-[5px] rounded-[3px] bg-accent/15" />
      <div className="absolute inset-[10px] rounded-[2px] bg-accent" />
    </div>
  );
}
