// frontend/src/components/layout/Sidebar.tsx
'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  {
    label: 'Home',
    href: '/',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    label: 'Replays',
    href: '/replays',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    label: 'Sessions',
    href: '/sessions',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
    ),
  },
  {
    label: 'Trends',
    href: '/trends',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
      </svg>
    ),
  },
  {
    label: 'Compare',
    href: '/compare',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    label: 'AI Coach',
    href: '/coach',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
    pro: true,
  },
];

const bottomNavItems = [
  {
    label: 'Settings',
    href: '/settings',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const sidebarRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Handle Escape key and focus management for mobile overlay
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    closeButtonRef.current?.focus();

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-void/80 backdrop-blur-sm z-40 lg:hidden animate-fade-in"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        ref={sidebarRef}
        className={`
          fixed top-0 left-0 z-50 h-full w-72
          glass-elevated
          transform transition-all duration-300 ease-out
          lg:translate-x-0 lg:static lg:z-auto
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        aria-label="Main navigation"
      >
        {/* Gradient border effect */}
        <div className="absolute inset-y-0 right-0 w-px bg-gradient-to-b from-boost/20 via-fire/10 to-transparent" />

        {/* Logo */}
        <div className="flex items-center justify-between h-18 px-6">
          <Link
            href="/"
            className="flex items-center gap-3 group focus:outline-none focus-visible:ring-2 focus-visible:ring-boost rounded-xl p-1 -m-1"
          >
            {/* Logo mark with animated glow */}
            <div className="relative">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fire to-fire-600 flex items-center justify-center logo-shine shadow-glow-fire group-hover:shadow-glow-fire-lg transition-shadow duration-300">
                <span className="text-white font-display text-xl tracking-wider">RL</span>
              </div>
              {/* Pulse ring on hover */}
              <div className="absolute inset-0 rounded-xl border-2 border-fire/50 opacity-0 group-hover:opacity-100 group-hover:animate-pulse-ring transition-opacity" />
            </div>
            <div className="flex flex-col">
              <span className="text-xl font-semibold text-white tracking-tight">rlcoach</span>
              <span className="text-[10px] uppercase tracking-widest text-white/40 font-medium">Performance Analytics</span>
            </div>
          </Link>

          {/* Mobile close button */}
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="lg:hidden p-2.5 text-white/60 hover:text-white rounded-xl hover:bg-white/5 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-boost"
            aria-label="Close navigation menu"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Divider with glow */}
        <div className="mx-6 divider-glow" />

        {/* Navigation */}
        <nav className="flex flex-col h-[calc(100%-4.5rem)] px-4 py-4" aria-label="Dashboard navigation">
          <div className="flex-1 space-y-1">
            {navItems.map((item, index) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  aria-current={isActive ? 'page' : undefined}
                  className={`
                    relative flex items-center gap-3 px-4 py-3 rounded-xl
                    transition-all duration-200 group
                    focus:outline-none focus-visible:ring-2 focus-visible:ring-boost
                    ${isActive
                      ? 'bg-gradient-to-r from-fire/20 to-fire/5 text-white'
                      : 'text-white/60 hover:text-white hover:bg-white/5'
                    }
                  `}
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  {/* Active indicator */}
                  {isActive && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 rounded-r-full bg-gradient-to-b from-fire to-fire-600 shadow-glow-fire" />
                  )}

                  {/* Icon with glow on active */}
                  <span className={`transition-all duration-200 ${isActive ? 'text-fire drop-shadow-[0_0_8px_rgba(255,107,53,0.5)]' : 'group-hover:text-white'}`}>
                    {item.icon}
                  </span>

                  <span className="font-medium">{item.label}</span>

                  {item.pro && (
                    <span className="ml-auto badge badge-fire text-[10px]">
                      PRO
                    </span>
                  )}

                  {/* Hover effect */}
                  {!isActive && (
                    <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-boost/0 to-boost/0 group-hover:from-boost/5 group-hover:to-transparent transition-all duration-300 pointer-events-none" />
                  )}
                </Link>
              );
            })}
          </div>

          {/* Bottom section */}
          <div className="pt-4 space-y-1">
            {/* Divider */}
            <div className="mx-2 mb-3 divider-glow" />

            {bottomNavItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  aria-current={isActive ? 'page' : undefined}
                  className={`
                    relative flex items-center gap-3 px-4 py-3 rounded-xl
                    transition-all duration-200 group
                    focus:outline-none focus-visible:ring-2 focus-visible:ring-boost
                    ${isActive
                      ? 'bg-gradient-to-r from-fire/20 to-fire/5 text-white'
                      : 'text-white/60 hover:text-white hover:bg-white/5'
                    }
                  `}
                >
                  {isActive && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 rounded-r-full bg-gradient-to-b from-fire to-fire-600 shadow-glow-fire" />
                  )}
                  <span className={`transition-all duration-200 ${isActive ? 'text-fire drop-shadow-[0_0_8px_rgba(255,107,53,0.5)]' : 'group-hover:text-white'}`}>
                    {item.icon}
                  </span>
                  <span className="font-medium">{item.label}</span>
                </Link>
              );
            })}

            {/* Version indicator */}
            <div className="mt-4 px-4 py-3 flex items-center gap-2 text-white/50">
              <div className="w-2 h-2 rounded-full bg-victory animate-pulse" />
              <span className="text-xs font-medium">v0.1.0</span>
            </div>
          </div>
        </nav>
      </aside>
    </>
  );
}
