// frontend/src/app/(dashboard)/settings/page.tsx
'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import Link from 'next/link';
import Image from 'next/image';

export default function SettingsPage() {
  const { data: session } = useSession();
  const [sessionGap, setSessionGap] = useState(30);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const user = session?.user as { id?: string; name?: string | null; email?: string | null; image?: string | null; subscriptionTier?: string } | undefined;
  // Check subscription tier from session (auth.ts exposes it in session.user.subscriptionTier)
  const isPro = user?.subscriptionTier === 'pro';

  const handleManageSubscription = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/stripe/create-portal', {
        method: 'POST',
      });
      const { url, error: apiError } = await res.json();
      if (url) {
        window.location.href = url;
      } else if (apiError) {
        setError('Unable to open subscription portal. Please try again.');
      }
    } catch {
      setError('Unable to connect. Check your internet connection.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-gray-400 mt-1">Manage your account and preferences</p>
      </div>

      <div className="space-y-8">
        {/* Profile Section */}
        <section className="bg-gray-900/50 border border-gray-800 rounded-xl p-6" aria-labelledby="profile-heading">
          <h2 id="profile-heading" className="text-lg font-semibold text-white mb-4">Profile</h2>
          <div className="flex items-center gap-4">
            {user?.image ? (
              <Image
                src={user.image}
                alt=""
                width={64}
                height={64}
                className="rounded-full"
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-gray-700 flex items-center justify-center" aria-hidden="true">
                <span className="text-2xl font-medium text-gray-300">
                  {user?.name?.[0]?.toUpperCase() || 'U'}
                </span>
              </div>
            )}
            <div>
              <p className="text-lg font-medium text-white">{user?.name || 'User'}</p>
              <p className="text-sm text-gray-400">{user?.email || 'No email'}</p>
            </div>
          </div>
        </section>

        {/* Subscription Section */}
        <section className="bg-gray-900/50 border border-gray-800 rounded-xl p-6" aria-labelledby="subscription-heading">
          <h2 id="subscription-heading" className="text-lg font-semibold text-white mb-4">Subscription</h2>
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center justify-between" role="alert">
              <span className="text-sm text-red-400">{error}</span>
              <button
                onClick={() => setError(null)}
                className="text-red-400 hover:text-red-300 focus:outline-none"
                aria-label="Dismiss error"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white font-medium">
                {isPro ? 'Pro' : 'Free'} Plan
              </p>
              <p className="text-sm text-gray-400">
                {isPro
                  ? 'Full access to AI Coach and all features'
                  : 'Unlimited replays and dashboard access'}
              </p>
            </div>
            {isPro ? (
              <button
                onClick={handleManageSubscription}
                disabled={isLoading}
                className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900 flex items-center gap-2"
              >
                {isLoading && (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                )}
                {isLoading ? 'Opening...' : 'Manage Subscription'}
              </button>
            ) : (
              <Link
                href="/upgrade"
                className="px-4 py-2 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900"
              >
                Upgrade to Pro
              </Link>
            )}
          </div>
        </section>

        {/* Linked Accounts Section */}
        <section className="bg-gray-900/50 border border-gray-800 rounded-xl p-6" aria-labelledby="accounts-heading">
          <h2 id="accounts-heading" className="text-lg font-semibold text-white mb-4">Linked Accounts</h2>
          <div className="space-y-3">
            {/* Discord */}
            <div className="flex items-center justify-between py-3 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-[#5865F2] flex items-center justify-center" aria-hidden="true">
                  <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
                  </svg>
                </div>
                <div>
                  <p className="text-white font-medium">Discord</p>
                  <p className="text-sm text-gray-400">Connected</p>
                </div>
              </div>
              <button className="text-sm text-gray-400 hover:text-white focus:outline-none focus:text-orange-400 focus:underline">
                Disconnect
              </button>
            </div>

            {/* Steam */}
            <div className="flex items-center justify-between py-3 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gray-700 flex items-center justify-center" aria-hidden="true">
                  <svg className="w-5 h-5 text-gray-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M12 2a10 10 0 0 0-9.97 9.286l5.39 2.225a2.835 2.835 0 0 1 1.6-.492c.06 0 .12.002.18.006l2.39-3.466v-.048a3.785 3.785 0 0 1 3.78-3.782 3.785 3.785 0 0 1 3.78 3.782 3.785 3.785 0 0 1-3.78 3.782h-.087l-3.41 2.44c0 .052.003.104.003.157a2.843 2.843 0 0 1-2.843 2.844 2.855 2.855 0 0 1-2.773-2.18L2.04 15.058A10 10 0 1 0 12 2z" />
                  </svg>
                </div>
                <div>
                  <p className="text-white font-medium">Steam</p>
                  <p className="text-sm text-gray-400">Not connected</p>
                </div>
              </div>
              <button className="text-sm text-orange-400 hover:text-orange-300 focus:outline-none focus:underline">
                Connect
              </button>
            </div>

            {/* Google */}
            <div className="flex items-center justify-between py-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gray-700 flex items-center justify-center" aria-hidden="true">
                  <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden="true">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                </div>
                <div>
                  <p className="text-white font-medium">Google</p>
                  <p className="text-sm text-gray-400">Not connected</p>
                </div>
              </div>
              <button className="text-sm text-orange-400 hover:text-orange-300 focus:outline-none focus:underline">
                Connect
              </button>
            </div>
          </div>
        </section>

        {/* Preferences Section */}
        <section className="bg-gray-900/50 border border-gray-800 rounded-xl p-6" aria-labelledby="preferences-heading">
          <h2 id="preferences-heading" className="text-lg font-semibold text-white mb-4">Preferences</h2>
          <div className="space-y-4">
            <div>
              <label htmlFor="session-gap" className="block text-sm text-gray-400 mb-2">
                Session Gap (minutes)
              </label>
              <p id="session-gap-hint" className="text-xs text-gray-500 mb-2">
                Replays within this time window are grouped into the same session
              </p>
              <input
                id="session-gap"
                type="number"
                value={sessionGap}
                onChange={(e) => setSessionGap(Number(e.target.value))}
                min={5}
                max={120}
                aria-describedby="session-gap-hint"
                className="w-24 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
              />
            </div>
          </div>
        </section>

        {/* Data Section */}
        <section className="bg-gray-900/50 border border-gray-800 rounded-xl p-6" aria-labelledby="data-heading">
          <h2 id="data-heading" className="text-lg font-semibold text-white mb-4">Your Data</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white font-medium">Export Data</p>
                <p className="text-sm text-gray-400">Download all your replay data</p>
              </div>
              <button className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900">
                Export
              </button>
            </div>
            <div className="flex items-center justify-between pt-4 border-t border-gray-800">
              <div>
                <p className="text-red-400 font-medium">Delete Account</p>
                <p className="text-sm text-gray-400">Permanently delete your account and data</p>
              </div>
              <button className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 focus:ring-offset-gray-900">
                Delete
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
