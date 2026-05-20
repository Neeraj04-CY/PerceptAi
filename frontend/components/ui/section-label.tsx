import { cn } from "@/lib/utils";

export function SectionLabel({
  children,
  className,
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "span" | "h2" | "h3";
}) {
  return (
    <Tag
      className={cn(
        "font-mono text-[10px] uppercase tracking-[0.22em] text-white/40",
        className
      )}
    >
      {children}
    </Tag>
  );
}
