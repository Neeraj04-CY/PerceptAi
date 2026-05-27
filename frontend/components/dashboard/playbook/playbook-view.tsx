"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PageHeader } from "@/components/ui/page-header";
import { templates, type PlaybookTemplate } from "@/lib/playbook-templates";
import { TemplateCard } from "./template-card";
import { pageEntry, staggerContainer } from "@/lib/motion";
import { cn } from "@/lib/utils";

type Category = "all" | "Research" | "Productivity" | "System" | "Custom";

const CATEGORIES: { label: string; value: Category }[] = [
  { label: "All", value: "all" },
  { label: "Research", value: "Research" },
  { label: "Productivity", value: "Productivity" },
  { label: "System", value: "System" },
  { label: "Custom", value: "Custom" },
];

export function PlaybookView() {
  const [filter, setFilter] = useState<Category>("all");

  const { regular, custom } = useMemo(() => {
    const filtered =
      filter === "all"
        ? templates
        : templates.filter((t) => t.category === filter);
    const custom = filtered.find((t) => t.id === "custom") || null;
    const regular = filtered.filter((t) => t.id !== "custom");
    return { regular, custom };
  }, [filter]);

  return (
    <motion.div {...pageEntry} className="space-y-7">
      <PageHeader
        eyebrow="Templates"
        title="Playbook"
        description="Ready-to-run agent templates. One click and you&apos;re shipping perception."
      />

      {/* Category filter */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="playbook-filter">
        {CATEGORIES.map((c) => {
          const active = filter === c.value;
          return (
            <button
              key={c.value}
              onClick={() => setFilter(c.value)}
              data-testid={`playbook-filter-${c.value}`}
              className={cn(
                "rounded-full h-8 px-3.5 text-[11.5px] font-medium transition-colors",
                active
                  ? "bg-accent text-black"
                  : "border border-white/[0.10] bg-white/[0.02] text-white/65 hover:text-white hover:border-white/20"
              )}
            >
              {c.label}
            </button>
          );
        })}
      </div>

      {/* Grid */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
      >
        <AnimatePresence initial={false} mode="popLayout">
          {regular.map((t) => (
            <TemplateCard key={t.id + filter} template={t} />
          ))}
          {custom && (
            <TemplateCard key={custom.id + filter} template={custom} fullWidth />
          )}
          {!regular.length && !custom && <NoMatch key="no-match" />}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

function NoMatch() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="md:col-span-2 rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl px-6 py-12 text-center"
    >
      <div className="text-[13px] text-white/55">
        No templates in this category yet.
      </div>
      <div className="mt-1 text-[12px] text-white/35">
        Pick another filter or run a custom task.
      </div>
    </motion.div>
  );
}
