// frontend/src/app/preview/page.tsx
// Development preview page to view dashboard UI without authentication
'use client';

import { useState } from 'react';
import { SessionProvider } from 'next-auth/react';
import { Sidebar } from '@/components/layout/Sidebar';
import { Navbar } from '@/components/layout/Navbar';
import { UploadModal } from '@/components/layout/UploadModal';
import { ToastProvider } from '@/components/Toast';

// Mock stat data for preview
const mockStats = {
  goals: 2.4,
  assists: 1.8,
  saves: 3.2,
  shots: 5.6,
  score: 485,
  mvps: 0.4,
};

function StatCard({
  label,
  value,
  trend,
  accentColor = 'boost',
  delay = 0,
}: {
  label: string;
  value: string | number;
  trend?: { value: number; direction: 'up' | 'down' };
  accentColor?: 'boost' | 'fire' | 'plasma' | 'victory';
  delay?: number;
}) {
  const colorClasses = {
    boost: 'from-boost/20 to-boost/5 border-boost/30 shadow-glow-sm',
    fire: 'from-fire/20 to-fire/5 border-fire/30',
    plasma: 'from-plasma/20 to-plasma/5 border-plasma/30',
    victory: 'from-victory/20 to-victory/5 border-victory/30',
  };

  return (
    <div
      className={`
        group relative overflow-hidden rounded-2xl border
        bg-gradient-to-br ${colorClasses[accentColor]}
        p-5 transition-all duration-300
        hover:scale-[1.02] hover:shadow-lg
        animate-slide-up opacity-0 [animation-fill-mode:forwards]
      `}
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Speed lines effect on hover */}
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
        <div className="absolute top-1/2 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/20 to-transparent transform -translate-y-1/2" />
      </div>

      <div className="relative">
        <p className="stat-label mb-2">{label}</p>
        <div className="flex items-end gap-3">
          <span className="stat-value text-4xl">{value}</span>
          {trend && (
            <span
              className={`
                text-sm font-semibold pb-1
                ${trend.direction === 'up' ? 'text-victory' : 'text-defeat'}
              `}
            >
              {trend.direction === 'up' ? '↑' : '↓'} {Math.abs(trend.value)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function QuickActionCard({
  icon,
  title,
  description,
  variant = 'default',
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  variant?: 'primary' | 'default';
}) {
  return (
    <button
      className={`
        group relative overflow-hidden rounded-2xl p-5 text-left
        transition-all duration-300 hover:scale-[1.02]
        ${variant === 'primary'
          ? 'bg-gradient-to-br from-fire/20 to-fire/5 border border-fire/30 hover:border-fire/50'
          : 'bg-white/[0.03] border border-white/5 hover:border-white/10 hover:bg-white/[0.05]'
        }
      `}
    >
      <div className="flex items-start gap-4">
        <div
          className={`
            w-12 h-12 rounded-xl flex items-center justify-center
            ${variant === 'primary'
              ? 'bg-fire/20 text-fire'
              : 'bg-white/5 text-white/60 group-hover:text-white'
            }
            transition-colors duration-200
          `}
        >
          {icon}
        </div>
        <div>
          <h3 className="font-semibold text-white mb-1">{title}</h3>
          <p className="text-sm text-white/50">{description}</p>
        </div>
      </div>
    </button>
  );
}

export default function PreviewPage() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  return (
    <SessionProvider>
      <ToastProvider>
        <div className="flex h-screen overflow-hidden noise">
          {/* Sidebar */}
          <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

          {/* Main content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Navbar */}
            <Navbar
              onMenuClick={() => setSidebarOpen(true)}
              onUploadClick={() => setUploadModalOpen(true)}
            />

            {/* Page content */}
            <main className="flex-1 overflow-y-auto">
              <div className="p-6 lg:p-8 space-y-8">
                {/* Header */}
                <div className="animate-fade-in">
                  <h1 className="text-4xl font-display text-white tracking-wide mb-2">
                    COMMAND CENTER
                  </h1>
                  <p className="text-white/50">
                    Preview of premium dashboard UI
                  </p>
                </div>

                {/* Stats Grid */}
                <section>
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-1 h-6 rounded-full bg-gradient-to-b from-boost to-boost/50" />
                    <h2 className="text-lg font-semibold text-white/80">Performance Overview</h2>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <StatCard label="Goals/Game" value={mockStats.goals} trend={{ value: 12, direction: 'up' }} accentColor="fire" delay={100} />
                    <StatCard label="Assists/Game" value={mockStats.assists} trend={{ value: 5, direction: 'up' }} accentColor="boost" delay={150} />
                    <StatCard label="Saves/Game" value={mockStats.saves} trend={{ value: 8, direction: 'up' }} accentColor="victory" delay={200} />
                    <StatCard label="Shots/Game" value={mockStats.shots} trend={{ value: 3, direction: 'down' }} accentColor="plasma" delay={250} />
                    <StatCard label="Avg Score" value={mockStats.score} accentColor="boost" delay={300} />
                    <StatCard label="MVPs/Game" value={mockStats.mvps} accentColor="fire" delay={350} />
                  </div>
                </section>

                {/* Quick Actions */}
                <section>
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-1 h-6 rounded-full bg-gradient-to-b from-fire to-fire/50" />
                    <h2 className="text-lg font-semibold text-white/80">Quick Actions</h2>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <QuickActionCard
                      variant="primary"
                      icon={
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                      }
                      title="Upload Replay"
                      description="Drop your .replay files for instant analysis"
                    />
                    <QuickActionCard
                      icon={
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                      }
                      title="View Trends"
                      description="Track your improvement over time"
                    />
                    <QuickActionCard
                      icon={
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                      }
                      title="AI Coach"
                      description="Get personalized coaching insights"
                    />
                  </div>
                </section>

                {/* Sample Card */}
                <section>
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-1 h-6 rounded-full bg-gradient-to-b from-plasma to-plasma/50" />
                    <h2 className="text-lg font-semibold text-white/80">Glass Card Examples</h2>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="card">
                      <h3 className="text-lg font-semibold text-white mb-2">Standard Card</h3>
                      <p className="text-white/60">
                        This is the default card style with glass morphism effect and subtle glow border.
                      </p>
                    </div>
                    <div className="glass-elevated rounded-2xl p-6 relative">
                      <div className="absolute inset-0 glow-border rounded-2xl pointer-events-none" />
                      <h3 className="text-lg font-semibold text-white mb-2">Elevated Glass</h3>
                      <p className="text-white/60">
                        A more prominent glass effect with enhanced backdrop blur and glow border.
                      </p>
                    </div>
                  </div>
                </section>

                {/* Buttons */}
                <section>
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-1 h-6 rounded-full bg-gradient-to-b from-victory to-victory/50" />
                    <h2 className="text-lg font-semibold text-white/80">Button Styles</h2>
                  </div>

                  <div className="flex flex-wrap gap-4">
                    <button className="btn-primary">Primary Button</button>
                    <button className="btn-secondary">Secondary Button</button>
                    <span className="badge badge-boost">Boost Badge</span>
                    <span className="badge badge-fire">Fire Badge</span>
                    <span className="badge badge-victory">Victory Badge</span>
                    <span className="badge badge-defeat">Defeat Badge</span>
                  </div>
                </section>
              </div>
            </main>
          </div>

          {/* Upload Modal */}
          <UploadModal
            isOpen={uploadModalOpen}
            onClose={() => setUploadModalOpen(false)}
          />
        </div>
      </ToastProvider>
    </SessionProvider>
  );
}
