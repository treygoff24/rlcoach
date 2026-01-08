// frontend/src/app/gdpr/page.tsx
/**
 * GDPR Data Removal Request Page
 *
 * Public form for third parties to request removal of their data
 * from replays where they appear as a player.
 */

'use client';

import { useState } from 'react';
import Link from 'next/link';

type IdentifierType = 'steam_id' | 'epic_id' | 'display_name';

interface FormData {
  player_identifier: string;
  identifier_type: IdentifierType;
  email: string;
  reason: string;
}

interface SubmitResult {
  status: string;
  request_id: string;
  message: string;
  affected_replays: number;
}

export default function GDPRRemovalPage() {
  const [formData, setFormData] = useState<FormData>({
    player_identifier: '',
    identifier_type: 'display_name',
    email: '',
    reason: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch('/api/v1/gdpr/removal-request', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to submit request');
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-block mb-4">
            <h1 className="text-3xl font-bold text-white">
              RL<span className="text-orange-500">Coach</span>
            </h1>
          </Link>
          <h2 className="text-2xl font-semibold text-white mb-2">
            GDPR Data Removal Request
          </h2>
          <p className="text-gray-400">
            Request removal of your player data from replays on our platform
          </p>
        </div>

        {/* Success Message */}
        {result && (
          <div className="bg-green-500/10 border border-green-500/50 rounded-lg p-6 mb-8">
            <h3 className="text-lg font-semibold text-green-400 mb-2">
              Request Submitted
            </h3>
            <p className="text-gray-300 mb-4">{result.message}</p>
            <div className="text-sm text-gray-400">
              <p>
                <strong>Request ID:</strong> {result.request_id}
              </p>
              <p>
                <strong>Affected Replays:</strong> {result.affected_replays}
              </p>
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4 mb-8">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {/* Form */}
        {!result && (
          <form onSubmit={handleSubmit} className="bg-gray-800 rounded-lg p-6 space-y-6">
            {/* Player Identifier */}
            <div>
              <label htmlFor="player_identifier" className="block text-sm font-medium text-gray-300 mb-2">
                Your Player Identifier
              </label>
              <input
                type="text"
                id="player_identifier"
                required
                value={formData.player_identifier}
                onChange={(e) =>
                  setFormData({ ...formData, player_identifier: e.target.value })
                }
                placeholder="Enter your Steam ID, Epic ID, or display name"
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
              />
            </div>

            {/* Identifier Type */}
            <div>
              <label htmlFor="identifier_type" className="block text-sm font-medium text-gray-300 mb-2">
                Identifier Type
              </label>
              <select
                id="identifier_type"
                value={formData.identifier_type}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    identifier_type: e.target.value as IdentifierType,
                  })
                }
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
              >
                <option value="display_name">Display Name</option>
                <option value="steam_id">Steam ID</option>
                <option value="epic_id">Epic Games ID</option>
              </select>
              <p className="mt-1 text-xs text-gray-500">
                Display name matches are case-insensitive
              </p>
            </div>

            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-2">
                Contact Email
              </label>
              <input
                type="email"
                id="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="you@example.com"
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
              />
              <p className="mt-1 text-xs text-gray-500">
                We&apos;ll send confirmation to this email when your request is processed
              </p>
            </div>

            {/* Reason */}
            <div>
              <label htmlFor="reason" className="block text-sm font-medium text-gray-300 mb-2">
                Reason (Optional)
              </label>
              <textarea
                id="reason"
                rows={3}
                value={formData.reason}
                onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                placeholder="Why are you requesting data removal?"
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent resize-none"
              />
            </div>

            {/* Info Box */}
            <div className="bg-gray-700/50 rounded-lg p-4 text-sm text-gray-400">
              <h4 className="font-medium text-gray-300 mb-2">What happens next:</h4>
              <ul className="list-disc list-inside space-y-1">
                <li>Your request will be reviewed within 30 days (GDPR requirement)</li>
                <li>Your player name and IDs will be anonymized in matching replays</li>
                <li>Statistical data may be retained in aggregate form</li>
                <li>You&apos;ll receive confirmation by email once processed</li>
              </ul>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className={`w-full py-3 px-4 font-medium rounded-lg transition-colors ${
                isSubmitting
                  ? 'bg-gray-600 text-gray-400 cursor-not-allowed'
                  : 'bg-orange-500 hover:bg-orange-600 text-white'
              }`}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Removal Request'}
            </button>
          </form>
        )}

        {/* Back Link */}
        <div className="mt-8 text-center">
          <Link href="/" className="text-gray-400 hover:text-orange-500 transition-colors">
            Back to RLCoach
          </Link>
        </div>

        {/* Privacy Notice */}
        <div className="mt-8 text-center text-xs text-gray-500">
          <p>
            This form is provided in compliance with GDPR Article 17 (Right to Erasure).
            For questions, contact{' '}
            <a href="mailto:privacy@rlcoach.gg" className="text-orange-500 hover:underline">
              privacy@rlcoach.gg
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
