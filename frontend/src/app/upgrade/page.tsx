/**
 * Upgrade page for free users trying to access Pro features.
 *
 * Redirects to Stripe checkout for Pro subscription.
 */

'use client';

import Link from 'next/link';
import { useState } from 'react';

export default function UpgradePage() {
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleUpgrade = async () => {
    setError(null);
    setIsLoading(true);
    try {
      const res = await fetch('/api/stripe/create-checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        throw new Error('Unable to start checkout. Please try again.');
      }
      const { url } = await res.json();
      if (url) {
        window.location.href = url;
        return;
      }
      throw new Error('Checkout is unavailable. Please try again later.');
    } catch (error) {
      console.error('Failed to create checkout session:', error);
      setError(error instanceof Error ? error.message : 'Unable to start checkout.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      <div className="max-w-lg w-full space-y-8 p-8">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white mb-4">
            Unlock AI Coach
          </h1>
          <p className="text-gray-400">
            Get personalized coaching powered by Claude Opus 4.5
          </p>
        </div>

        {/* Pro Features */}
        <div className="bg-gray-800/50 border border-orange-500/30 rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold text-white">Pro</span>
            <span className="text-3xl font-bold text-orange-500">
              $10<span className="text-lg text-gray-400">/mo</span>
            </span>
          </div>

          <ul className="space-y-3">
            <li className="flex items-center gap-3 text-gray-300">
              <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              AI Coach with Claude Opus 4.5
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Extended thinking for deep analysis
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Personalized coaching notes
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Coach memory across sessions
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Priority support
            </li>
          </ul>

          <button
            onClick={handleUpgrade}
            disabled={isLoading}
            className="w-full py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
          >
            {isLoading ? 'Starting checkout...' : 'Upgrade to Pro'}
          </button>
          {error && (
            <p className="text-sm text-red-400 text-center" role="alert">
              {error}
            </p>
          )}
        </div>

        {/* Free Tier Reminder */}
        <div className="text-center space-y-4">
          <p className="text-gray-500 text-sm">
            Free tier includes unlimited replay uploads and full dashboard access
          </p>
          <Link
            href="/dashboard"
            className="text-orange-500 hover:underline text-sm"
          >
            ← Back to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
