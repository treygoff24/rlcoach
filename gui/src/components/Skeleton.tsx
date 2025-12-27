interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse bg-[var(--color-bg-tertiary)] rounded ${className}`}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      <div className="flex gap-4 p-3 border-b border-[var(--color-border)]">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 flex-1" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 p-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 flex-1" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart() {
  return (
    <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4">
      <Skeleton className="h-6 w-32 mb-4" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
