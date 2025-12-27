interface CardProps {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-[var(--color-bg-secondary)] rounded-lg border border-[var(--color-border)] ${className}`}>
      {children}
    </div>
  );
}

interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export function CardHeader({ children, className = '' }: CardHeaderProps) {
  return (
    <div className={`px-4 py-3 border-b border-[var(--color-border)] ${className}`}>
      {children}
    </div>
  );
}

interface CardContentProps {
  children: React.ReactNode;
  className?: string;
}

export function CardContent({ children, className = '' }: CardContentProps) {
  return (
    <div className={`p-4 ${className}`}>
      {children}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
}

export function StatCard({ label, value, subtitle, trend, trendValue }: StatCardProps) {
  const trendColors = {
    up: 'text-[var(--color-success)]',
    down: 'text-[var(--color-error)]',
    neutral: 'text-[var(--color-text-muted)]',
  };

  return (
    <Card className="p-4">
      <div className="text-sm text-[var(--color-text-muted)] mb-1">{label}</div>
      <div className="text-2xl font-bold text-[var(--color-text)]">{value}</div>
      {(subtitle || trendValue) && (
        <div className="flex items-center gap-2 mt-1">
          {subtitle && (
            <span className="text-xs text-[var(--color-text-muted)]">{subtitle}</span>
          )}
          {trend && trendValue && (
            <span className={`text-xs ${trendColors[trend]}`}>
              {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'} {trendValue}
            </span>
          )}
        </div>
      )}
    </Card>
  );
}
