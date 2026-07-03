"use client";

import { motion } from "framer-motion";
import { FileText, Lightbulb, ArrowRight, Link2, ShieldCheck, ShieldAlert } from "lucide-react";
import type { ApiTaskReport } from "@/lib/api";

/**
 * The business deliverable of a session. This card answers ONE question:
 * "what did I get?" — before any steps or logs.
 */
export function ReportCard({ report }: { report: ApiTaskReport }) {
  const confidencePct = Math.round((report.confidence ?? 0) * 100);
  const confident = confidencePct >= 70;

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      data-testid="report-card"
      className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 text-white/70">
          <FileText size={14} />
          <span className="text-[11px] font-medium uppercase tracking-[0.14em]">Report</span>
        </div>
        <div
          data-testid="report-confidence"
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-mono tabular-nums ${
            confident
              ? "bg-accent/10 text-accent"
              : "bg-[#E8C44A]/10 text-[#E8C44A]"
          }`}
          title="Confidence combines verification and evidence quality"
        >
          {confident ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
          {confidencePct}% confidence
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Executive summary */}
        <p
          data-testid="report-summary"
          className="text-[14px] leading-relaxed text-white/90 max-w-3xl"
        >
          {report.executive_summary}
        </p>

        {/* Key findings */}
        {report.key_findings?.length > 0 && (
          <div data-testid="report-findings">
            <SectionLabel icon={<Lightbulb size={12} />} text="Key findings" />
            <ul className="mt-2 space-y-1.5">
              {report.key_findings.map((finding, i) => (
                <li key={i} className="flex gap-2.5 text-[13px] text-white/75 leading-relaxed">
                  <span className="mt-[7px] h-1 w-1 rounded-full bg-accent shrink-0" />
                  {finding}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Evidence table */}
        {report.evidence?.length > 0 && (
          <div data-testid="report-evidence">
            <SectionLabel icon={<FileText size={12} />} text={`Evidence · ${report.evidence.length}`} />
            <div className="mt-2 rounded-lg border border-white/[0.07] overflow-x-auto">
              <table className="w-full text-left text-[12.5px]">
                <thead>
                  <tr className="border-b border-white/[0.06] text-white/40">
                    <th className="px-3 py-2 font-medium uppercase tracking-wider text-[10px]">Kind</th>
                    <th className="px-3 py-2 font-medium uppercase tracking-wider text-[10px]">Label</th>
                    <th className="px-3 py-2 font-medium uppercase tracking-wider text-[10px]">Value</th>
                    <th className="px-3 py-2 font-medium uppercase tracking-wider text-[10px]">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {report.evidence.map((item, i) => (
                    <tr key={i} className="border-b border-white/[0.04] last:border-0">
                      <td className="px-3 py-2">
                        <span className="inline-flex rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10.5px] uppercase text-white/60">
                          {item.kind}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-white/60">{item.label}</td>
                      <td className="px-3 py-2 text-white/90 font-medium max-w-[280px] truncate" title={item.value}>
                        {item.value}
                      </td>
                      <td className="px-3 py-2 text-white/45 font-mono text-[11px] max-w-[160px] truncate" title={item.source}>
                        {item.source || "screen"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Sources + next actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {report.sources?.length > 0 && (
            <div data-testid="report-sources">
              <SectionLabel icon={<Link2 size={12} />} text="Sources" />
              <ul className="mt-2 space-y-1">
                {report.sources.map((source, i) => (
                  <li key={i} className="font-mono text-[11.5px] text-white/50 truncate" title={source}>
                    {source}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.next_actions?.length > 0 && (
            <div data-testid="report-next-actions">
              <SectionLabel icon={<ArrowRight size={12} />} text="Suggested next" />
              <ul className="mt-2 space-y-1.5">
                {report.next_actions.map((action, i) => (
                  <li key={i} className="flex gap-2 text-[12.5px] text-white/65 leading-relaxed">
                    <ArrowRight size={12} className="mt-[3px] text-accent shrink-0" />
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </motion.section>
  );
}

function SectionLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 text-white/40">
      {icon}
      <span className="text-[10.5px] font-medium uppercase tracking-[0.14em]">{text}</span>
    </div>
  );
}
