"use client";

import { useMemo } from "react";

const TOKEN_RE =
  /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b(?:true|false|null)\b)|(-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)/g;

export function JsonViewer({ value }: { value: unknown }) {
  const text = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);

  const tokens = useMemo(() => {
    if (!text) return [];
    const out: { type: string; value: string }[] = [];
    let last = 0;
    let m: RegExpExecArray | null;
    TOKEN_RE.lastIndex = 0;
    while ((m = TOKEN_RE.exec(text)) !== null) {
      if (m.index > last) out.push({ type: "text", value: text.slice(last, m.index) });
      if (m[1]) out.push({ type: "key", value: m[1] });
      else if (m[2]) out.push({ type: "string", value: m[2] });
      else if (m[3]) out.push({ type: "bool", value: m[3] });
      else if (m[4]) out.push({ type: "number", value: m[4] });
      last = TOKEN_RE.lastIndex;
    }
    if (last < text.length) out.push({ type: "text", value: text.slice(last) });
    return out;
  }, [text]);

  return (
    <pre
      className="rounded-lg border border-white/[0.06] bg-[#080808] px-4 py-3 font-mono text-[11.5px] leading-[1.7] overflow-x-auto max-h-[320px] overflow-y-auto"
      data-testid="json-viewer"
    >
      <code>
        {tokens.map((t, i) => {
          if (t.type === "key")
            return (
              <span key={i} className="text-accent">
                {t.value}
              </span>
            );
          if (t.type === "string")
            return (
              <span key={i} className="text-[#A6E3FF]">
                {t.value}
              </span>
            );
          if (t.type === "number")
            return (
              <span key={i} className="text-[#E8C44A]">
                {t.value}
              </span>
            );
          if (t.type === "bool")
            return (
              <span key={i} className="text-[#FF9F7A]">
                {t.value}
              </span>
            );
          return (
            <span key={i} className="text-white/55">
              {t.value}
            </span>
          );
        })}
      </code>
    </pre>
  );
}
