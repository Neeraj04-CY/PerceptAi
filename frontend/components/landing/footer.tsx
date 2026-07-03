"use client";

import { motion } from "framer-motion";
import type { MouseEvent } from "react";
import Link from "next/link";
import { Github, Twitter, Linkedin } from "lucide-react";

const cols = [
  {
    title: "Product",
    links: [
      { label: "Perception API", href: "/dashboard" },
      { label: "Trace replay", href: "/dashboard/sessions" },
      { label: "Agent evals", href: "/dashboard" },
      { label: "Changelog", href: "https://github.com/Neeraj04-CY/PerceptAi" },
    ],
  },
  {
    title: "Developers",
    links: [
      { label: "Docs", href: "https://perceptai-production.up.railway.app/docs" },
      { label: "SDK reference", href: "https://pypi.org/project/perceptai/" },
      { label: "Status", href: "https://perceptai-production.up.railway.app/health" },
      { label: "Open source", href: "https://github.com/Neeraj04-CY/PerceptAi" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "https://github.com/Neeraj04-CY/PerceptAi" },
      { label: "Customers", href: "/signup" },
      { label: "Careers", href: "https://github.com/Neeraj04-CY/PerceptAi" },
      { label: "Contact", href: "mailto:neerajpatil0402@gmail.com" },
    ],
  },
];

export function Footer() {
  const handleScrollTop = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <footer
      className="relative border-t border-white/5 bg-black/40 pt-20 pb-10"
      data-testid="footer"
    >
      <div className="mx-auto max-w-container px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="grid lg:grid-cols-[1.4fr_repeat(3,1fr)] gap-12 lg:gap-8"
        >
          <div>
            <div className="flex items-center gap-2.5">
              <div className="relative h-8 w-8">
                <div className="absolute inset-0 rounded-md border border-accent/40" />
                <div className="absolute inset-[5px] rounded-[3px] bg-accent/15" />
                <div className="absolute inset-[10px] rounded-[2px] bg-accent" />
              </div>
              <span className="font-display tracking-[0.12em] text-lg text-white">
                PERCEPT<span className="text-accent">AI</span>
              </span>
            </div>
            <p className="mt-5 text-sm text-white/50 leading-relaxed max-w-sm">
              The perception layer for autonomous agents.
              Built in San Francisco for the next decade of AI infrastructure.
            </p>
            <div className="mt-6 flex items-center gap-2">
              {[Github, Twitter, Linkedin].map((Icon, i) => (
                <a
                  key={i}
                  href="#"
                  data-testid={`footer-social-${i}`}
                  className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-white/60 hover:text-accent hover:border-accent/40 transition-all duration-300"
                >
                  <Icon size={15} />
                </a>
              ))}
            </div>
          </div>

          {cols.map((col) => (
            <div key={col.title}>
              <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-white/35">
                {col.title}
              </div>
              <ul className="mt-5 space-y-3">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.href.startsWith("/") ? (
                      <Link
                        href={l.href}
                        data-testid={`footer-link-${l.label.toLowerCase().replace(/\s+/g, "-")}`}
                        className="text-sm text-white/65 hover:text-white transition-colors duration-300"
                      >
                        {l.label}
                      </Link>
                    ) : (
                      <a
                        href={l.href}
                        data-testid={`footer-link-${l.label.toLowerCase().replace(/\s+/g, "-")}`}
                        className="text-sm text-white/65 hover:text-white transition-colors duration-300"
                      >
                        {l.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </motion.div>

        <div className="mt-16 pt-8 border-t border-white/5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
          <div className="font-mono text-[11px] tracking-wider text-white/35">
            © {new Date().getFullYear()} PerceptAI Labs, Inc. All rights reserved.
          </div>
          <div className="flex items-center gap-5 font-mono text-[11px] tracking-wider text-white/35">
            <a href="#" onClick={handleScrollTop} className="hover:text-white/70 transition-colors">
              Privacy
            </a>
            <a href="#" onClick={handleScrollTop} className="hover:text-white/70 transition-colors">
              Terms
            </a>
            <a href="#" onClick={handleScrollTop} className="hover:text-white/70 transition-colors">
              Security
            </a>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
              All systems normal
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
