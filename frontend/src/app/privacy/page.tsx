// frontend/src/app/privacy/page.tsx
/**
 * Privacy Policy Page
 *
 * IMPORTANT: This is a template. Replace with actual privacy policy reviewed by a lawyer.
 */

import Link from 'next/link';

export const metadata = {
  title: 'Privacy Policy - RLCoach',
  description: 'Privacy Policy for RLCoach replay analysis platform',
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-md sticky top-0 z-50">
        <div className="mx-auto max-w-4xl px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold">
            RL<span className="text-orange-500">Coach</span>
          </Link>
          <Link href="/" className="text-gray-400 hover:text-white transition-colors text-sm">
            Back to Home
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-4xl px-4 py-12">
        <h1 className="text-3xl font-bold text-white mb-2">Privacy Policy</h1>
        <p className="text-gray-400 mb-8">Last updated: January 2026</p>

        <div className="prose prose-invert prose-gray max-w-none space-y-8">
          <section>
            <h2 className="text-xl font-semibold text-white mb-4">1. Introduction</h2>
            <p className="text-gray-300">
              RLCoach (&quot;we&quot;, &quot;our&quot;, or &quot;us&quot;) is committed to protecting your privacy.
              This Privacy Policy explains how we collect, use, disclose, and safeguard your information
              when you use our Rocket League replay analysis service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">2. Information We Collect</h2>

            <h3 className="text-lg font-medium text-white mt-4 mb-2">Account Information</h3>
            <p className="text-gray-300">
              When you sign in via OAuth (Discord or Google), we receive:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>Your display name and email address</li>
              <li>Profile picture URL</li>
              <li>OAuth provider identifier</li>
            </ul>

            <h3 className="text-lg font-medium text-white mt-4 mb-2">Replay Data</h3>
            <p className="text-gray-300">
              When you upload replay files, we process and store:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>Game metadata (map, duration, date, game mode)</li>
              <li>Player statistics and performance metrics</li>
              <li>Player identifiers (Steam ID, Epic ID, display names)</li>
              <li>Calculated analytics and coaching insights</li>
            </ul>

            <h3 className="text-lg font-medium text-white mt-4 mb-2">AI Coach Conversations</h3>
            <p className="text-gray-300">
              If you use the Pro AI Coach feature, we store:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>Your messages and questions</li>
              <li>AI-generated coaching advice</li>
              <li>Notes you save during coaching sessions</li>
            </ul>

            <h3 className="text-lg font-medium text-white mt-4 mb-2">Usage Data</h3>
            <p className="text-gray-300">
              We automatically collect:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>IP address and browser information</li>
              <li>Pages visited and features used</li>
              <li>Error logs for debugging</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">3. How We Use Your Information</h2>
            <ul className="list-disc list-inside text-gray-300 space-y-1">
              <li>Provide and improve our replay analysis service</li>
              <li>Generate personalized coaching insights</li>
              <li>Process payments for Pro subscriptions</li>
              <li>Send service-related communications</li>
              <li>Create aggregated benchmarks (anonymized)</li>
              <li>Debug issues and improve performance</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">4. Data Sharing</h2>
            <p className="text-gray-300">
              We do not sell your personal data. We share data only with:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li><strong>Stripe:</strong> Payment processing (billing data only)</li>
              <li><strong>Anthropic:</strong> AI coaching (conversation content for Pro users)</li>
              <li><strong>Cloud providers:</strong> Data storage and processing</li>
              <li><strong>Legal authorities:</strong> When required by law</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">5. Data Retention</h2>
            <p className="text-gray-300">
              We retain your data for as long as your account is active. When you delete your account:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>30-day grace period to cancel deletion</li>
              <li>Personal data is anonymized after grace period</li>
              <li>Aggregated statistics may be retained indefinitely</li>
              <li>Backup copies are purged within 90 days</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">6. Your Rights (GDPR)</h2>
            <p className="text-gray-300">
              Under GDPR, you have the right to:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li><strong>Access:</strong> Request a copy of your data (Settings &gt; Export Data)</li>
              <li><strong>Rectification:</strong> Correct inaccurate data</li>
              <li><strong>Erasure:</strong> Delete your account and data</li>
              <li><strong>Portability:</strong> Export data in machine-readable format</li>
              <li><strong>Objection:</strong> Object to certain processing activities</li>
            </ul>
            <p className="text-gray-300 mt-4">
              Third parties who appear in replays uploaded by others can request data removal via our{' '}
              <Link href="/gdpr" className="text-orange-500 hover:underline">
                GDPR Data Request
              </Link>{' '}
              form.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">7. Data Security</h2>
            <p className="text-gray-300">
              We implement industry-standard security measures:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>TLS encryption for all data in transit</li>
              <li>Encrypted database storage</li>
              <li>Regular security audits</li>
              <li>Access controls and monitoring</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">8. Cookies</h2>
            <p className="text-gray-300">
              We use essential cookies for:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>Authentication session management</li>
              <li>Security and fraud prevention</li>
            </ul>
            <p className="text-gray-300 mt-2">
              We do not use tracking or advertising cookies.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">9. Children&apos;s Privacy</h2>
            <p className="text-gray-300">
              RLCoach is not intended for children under 13. We do not knowingly collect personal
              information from children under 13. If you believe a child has provided us with personal
              data, please contact us.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">10. International Transfers</h2>
            <p className="text-gray-300">
              Your data may be processed in countries outside your residence. We ensure appropriate
              safeguards are in place for international transfers, including standard contractual clauses.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">11. Changes to This Policy</h2>
            <p className="text-gray-300">
              We may update this Privacy Policy from time to time. We will notify you of material
              changes via email or in-app notification. Continued use after changes constitutes
              acceptance.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">12. Contact Us</h2>
            <p className="text-gray-300">
              For privacy-related questions or to exercise your rights:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>
                Email:{' '}
                <a href="mailto:privacy@rlcoach.gg" className="text-orange-500 hover:underline">
                  privacy@rlcoach.gg
                </a>
              </li>
              <li>
                GDPR requests:{' '}
                <Link href="/gdpr" className="text-orange-500 hover:underline">
                  Submit a data request
                </Link>
              </li>
            </ul>
          </section>
        </div>

        {/* Footer */}
        <div className="mt-12 pt-8 border-t border-gray-800 text-center text-gray-500 text-sm">
          <p>
            <Link href="/terms" className="hover:text-orange-500 transition-colors">
              Terms of Service
            </Link>
            {' | '}
            <Link href="/gdpr" className="hover:text-orange-500 transition-colors">
              GDPR Data Request
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
