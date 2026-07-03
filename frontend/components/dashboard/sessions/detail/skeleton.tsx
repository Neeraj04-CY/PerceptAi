export function DetailSkeleton() {
  return (
    <div className="space-y-6 animate-pulse" data-testid="detail-skeleton">
      {/* Back */}
      <div className="h-4 w-24 rounded bg-white/[0.04]" />

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2 flex-1">
          <div className="h-6 w-3/4 rounded bg-white/[0.05]" />
          <div className="h-4 w-1/3 rounded bg-white/[0.04]" />
        </div>
        <div className="h-6 w-24 rounded-full bg-white/[0.05]" />
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-3">
            <div className="h-3 w-16 rounded bg-white/[0.05]" />
            <div className="h-5 w-24 rounded bg-white/[0.05]" />
          </div>
        ))}
      </div>

      {/* Timeline */}
      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-6 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-start gap-4">
            <div className="h-5 w-5 rounded-full bg-white/[0.05]" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-2/3 rounded bg-white/[0.05]" />
              <div className="h-3 w-1/3 rounded bg-white/[0.04]" />
            </div>
            <div className="h-3 w-12 rounded bg-white/[0.04]" />
          </div>
        ))}
      </div>

      {/* Logs */}
      <div className="rounded-xl border border-white/[0.08] bg-[#080808] p-4 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-3 rounded bg-white/[0.04]" style={{ width: `${78 - i * 6}%` }} />
        ))}
      </div>
    </div>
  );
}
