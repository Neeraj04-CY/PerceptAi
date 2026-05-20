export function SkeletonRow() {
  return (
    <div
      className="grid grid-cols-[1.8fr_120px_110px_110px_110px_24px] gap-3 px-5 py-4 border-b border-white/[0.04] last:border-0 items-center"
      data-testid="session-skeleton-row"
    >
      <Shimmer className="h-3.5 w-[78%] rounded" />
      <Shimmer className="h-5 w-20 rounded-full" />
      <Shimmer className="h-3 w-14 rounded" />
      <Shimmer className="h-3 w-10 rounded" />
      <Shimmer className="h-3 w-16 rounded" />
      <Shimmer className="h-3 w-3 rounded" />
    </div>
  );
}

function Shimmer({ className = "" }: { className?: string }) {
  return (
    <div
      className={
        "relative overflow-hidden bg-white/[0.04] " + className
      }
    >
      <div
        className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite]"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.06) 50%, transparent 100%)",
        }}
      />
    </div>
  );
}
