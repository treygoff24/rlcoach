// frontend/src/components/layout/Navbar.tsx
'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useSession, signOut } from 'next-auth/react';

interface NavbarProps {
  onMenuClick: () => void;
  onUploadClick: () => void;
}

export function Navbar({ onMenuClick, onUploadClick }: NavbarProps) {
  const { data: session } = useSession();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuItemsRef = useRef<(HTMLAnchorElement | HTMLButtonElement | null)[]>([]);

  const menuItems = [
    { type: 'link' as const, href: '/settings', label: 'Settings' },
    { type: 'button' as const, action: () => signOut({ callbackUrl: '/' }), label: 'Sign out' },
  ];

  // Handle menu keyboard navigation
  const handleMenuKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setFocusedIndex((prev) => (prev + 1) % menuItems.length);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex((prev) => (prev - 1 + menuItems.length) % menuItems.length);
        break;
      case 'Home':
        e.preventDefault();
        setFocusedIndex(0);
        break;
      case 'End':
        e.preventDefault();
        setFocusedIndex(menuItems.length - 1);
        break;
      case 'Escape':
        setShowUserMenu(false);
        buttonRef.current?.focus();
        break;
    }
  }, [menuItems.length]);

  // Focus menu item when focusedIndex changes
  useEffect(() => {
    if (showUserMenu && focusedIndex >= 0) {
      menuItemsRef.current[focusedIndex]?.focus();
    }
  }, [focusedIndex, showUserMenu]);

  // Reset focus index and focus first item when menu opens
  useEffect(() => {
    if (showUserMenu) {
      setFocusedIndex(0);
    } else {
      setFocusedIndex(-1);
    }
  }, [showUserMenu]);

  // Close dropdown on Escape key or focus out
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showUserMenu) {
        setShowUserMenu(false);
        buttonRef.current?.focus();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    };

    if (showUserMenu) {
      document.addEventListener('keydown', handleKeyDown);
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showUserMenu]);

  return (
    <header className="sticky top-0 z-30 h-18">
      {/* Glass background with gradient border */}
      <div className="absolute inset-0 glass" />
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />

      <div className="relative flex items-center justify-between h-full px-4 lg:px-6">
        {/* Left side */}
        <div className="flex items-center gap-4">
          {/* Mobile menu button */}
          <button
            onClick={onMenuClick}
            aria-label="Open navigation menu"
            className="lg:hidden p-2.5 text-white/60 hover:text-white rounded-xl hover:bg-white/5 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-boost"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>

        {/* Right side */}
        <div className="flex items-center gap-3">
          {/* Upload button - premium styled */}
          <button
            onClick={onUploadClick}
            className="group relative flex items-center gap-2.5 px-5 py-2.5 rounded-xl font-semibold text-white transition-all duration-300 overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-fire focus-visible:ring-offset-2 focus-visible:ring-offset-void"
          >
            {/* Gradient background */}
            <div className="absolute inset-0 bg-gradient-to-r from-fire to-fire-600 transition-all duration-300" />
            {/* Shine effect */}
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
            {/* Glow effect */}
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 shadow-glow-fire-lg" />

            <svg className="relative w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span className="relative hidden sm:inline">Upload Replay</span>
            <span className="sm:hidden sr-only">Upload replay</span>
          </button>

          {/* User menu */}
          {session?.user && (
            <div className="relative" ref={menuRef}>
              <button
                ref={buttonRef}
                id="user-menu-button"
                onClick={() => setShowUserMenu(!showUserMenu)}
                aria-expanded={showUserMenu}
                aria-haspopup="true"
                aria-label="User menu"
                className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-white/5 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-boost group"
              >
                {/* Avatar with ring effect */}
                <div className="relative">
                  {session.user.image ? (
                    <Image
                      src={session.user.image}
                      alt=""
                      width={36}
                      height={36}
                      className="rounded-xl ring-2 ring-white/10 group-hover:ring-boost/30 transition-all duration-200"
                    />
                  ) : (
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-surface to-elevated flex items-center justify-center ring-2 ring-white/10 group-hover:ring-boost/30 transition-all duration-200">
                      <span className="text-sm font-semibold text-white/80">
                        {session.user.name?.[0]?.toUpperCase() || 'U'}
                      </span>
                    </div>
                  )}
                  {/* Online indicator */}
                  <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-victory border-2 border-void" />
                </div>
                <svg className={`w-4 h-4 text-white/40 transition-transform duration-200 ${showUserMenu ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Dropdown menu */}
              {showUserMenu && (
                <div
                  className="absolute right-0 mt-2 w-64 rounded-2xl overflow-hidden animate-scale-in origin-top-right"
                  role="menu"
                  aria-orientation="vertical"
                  aria-labelledby="user-menu-button"
                  onKeyDown={handleMenuKeyDown}
                >
                  {/* Glass background */}
                  <div className="absolute inset-0 glass-elevated" />
                  <div className="absolute inset-0 glow-border rounded-2xl" />

                  {/* Content */}
                  <div className="relative">
                    {/* User info header */}
                    <div className="p-4 border-b border-white/5">
                      <div className="flex items-center gap-3">
                        {session.user.image ? (
                          <Image
                            src={session.user.image}
                            alt=""
                            width={40}
                            height={40}
                            className="rounded-xl"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-surface to-elevated flex items-center justify-center">
                            <span className="text-sm font-semibold text-white/80">
                              {session.user.name?.[0]?.toUpperCase() || 'U'}
                            </span>
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-white truncate">
                            {session.user.name}
                          </p>
                          <p className="text-sm text-white/50 truncate">
                            {session.user.email}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Menu items */}
                    <div className="p-2" role="none">
                      <Link
                        href="/settings"
                        ref={(el) => { menuItemsRef.current[0] = el; }}
                        onClick={() => setShowUserMenu(false)}
                        role="menuitem"
                        tabIndex={focusedIndex === 0 ? 0 : -1}
                        className="flex items-center gap-3 px-4 py-3 text-white/70 hover:text-white hover:bg-white/5 rounded-xl transition-all duration-200 focus:outline-none focus:bg-white/5 focus:text-white group"
                      >
                        <svg className="w-5 h-5 text-white/40 group-hover:text-boost transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <span className="font-medium">Settings</span>
                      </Link>
                      <button
                        ref={(el) => { menuItemsRef.current[1] = el; }}
                        onClick={() => signOut({ callbackUrl: '/' })}
                        role="menuitem"
                        tabIndex={focusedIndex === 1 ? 0 : -1}
                        className="flex items-center gap-3 w-full px-4 py-3 text-white/70 hover:text-white hover:bg-white/5 rounded-xl transition-all duration-200 focus:outline-none focus:bg-white/5 focus:text-white group"
                      >
                        <svg className="w-5 h-5 text-white/40 group-hover:text-defeat transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                        <span className="font-medium">Sign out</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
