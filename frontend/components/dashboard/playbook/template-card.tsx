"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { GlassCard } from "@/components/ui/glass-card";
import {
  resolveInstruction,
  type PlaybookTemplate,
  type Difficulty,
} from "@/lib/playbook-templates";
import { staggerItem } from "@/lib/motion";

const difficultyStyles: Record<Difficulty, string> = {
  simple: "bg-accent/10 text-accent",
  medium: "bg-[#E8C44A]/10 text-[#E8C44A]",
  custom: "bg-[#5BB1FF]/10 text-[#5BB1FF]",
};

interface Props {
  template: PlaybookTemplate;
  fullWidth?: boolean;
}

export function TemplateCard({ template, fullWidth = false }: Props) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const isCustom = template.id === "custom";

  const requiresInput = template.hasInput;
  const canRun =
    !requiresInput || value.trim().length > 0 || !!template.instruction;

  const handleRun = () => {
    if (!canRun) return;
    const finalInstruction = resolveInstruction(template, value);
    if (!finalInstruction.trim()) return;
    router.push(`/dashboard?task=${encodeURIComponent(finalInstruction)}`);
  };

  return (
    <motion.div
      variants={staggerItem}
      layout
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className={cn(fullWidth && "md:col-span-2")}
      data-testid={`template-card-${template.id}`}
    >
      <GlassCard
        padding="md"
        className="h-full flex flex-col gap-4 hover:border-white/15 transition-colors duration-300"
      >
        {/* Top row */}
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
            {template.category}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
            ≈ {template.estimatedTime}
          </span>
        </div>

        {/* Icon + Title + Description */}
        <div className="flex items-start gap-4">
          <span
            className="shrink-0 h-12 w-12 rounded-lg border border-white/[0.10] bg-white/[0.04] flex items-center justify-center text-[24px] leading-none"
            aria-hidden
          >
            {template.icon}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-[16px] font-semibold tracking-tight text-white leading-tight">
              {template.title}
            </h3>
            <p className="mt-1 text-[13px] text-white/55 leading-relaxed line-clamp-2">
              {template.description}
            </p>
          </div>
        </div>

        {/* Optional input */}
        {requiresInput && (
          <div>
            {template.inputLabel && (
              <label className="block mb-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
                {template.inputLabel}
              </label>
            )}
            {isCustom ? (
              <textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleRun();
                }}
                placeholder={template.inputPlaceholder}
                rows={3}
                data-testid={`template-input-${template.id}`}
                className="w-full resize-none rounded-lg border border-white/[0.08] bg-white/[0.02] px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white placeholder:text-white/30 focus:outline-none focus:border-accent/40 focus:bg-white/[0.03] focus:ring-1 focus:ring-accent/20 transition-all duration-200"
              />
            ) : (
              <Input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleRun();
                }}
                placeholder={template.inputPlaceholder}
                data-testid={`template-input-${template.id}`}
                className="h-10"
              />
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-auto flex items-center justify-between gap-3 pt-1">
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em]",
              difficultyStyles[template.difficulty]
            )}
          >
            {template.difficulty}
          </span>
          <button
            onClick={handleRun}
            disabled={!canRun}
            data-testid={`template-run-${template.id}`}
            className={cn(
              "group inline-flex items-center gap-1.5 rounded-full h-9 px-4 font-mono text-[11px] uppercase tracking-[0.18em] transition-all duration-300",
              canRun
                ? "bg-accent text-black hover:shadow-[0_0_30px_-8px_rgba(0,255,133,0.55)]"
                : "bg-white/[0.04] text-white/35 cursor-not-allowed"
            )}
          >
            {isCustom ? "Run custom task" : "Run this"}
            <ArrowRight
              size={12}
              className="transition-transform duration-300 group-hover:translate-x-0.5"
              strokeWidth={2.5}
            />
          </button>
        </div>
      </GlassCard>
    </motion.div>
  );
}
