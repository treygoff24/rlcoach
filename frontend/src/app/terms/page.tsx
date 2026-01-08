// frontend/src/app/terms/page.tsx
/**
 * Terms of Service Page
 *
 * IMPORTANT: This is a template. Replace with actual legal terms reviewed by a lawyer.
 */

import Link from 'next/link';

export const metadata = {
  title: 'Terms of Service - RLCoach',
  description: 'Terms of Service for RLCoach replay analysis platform',
};

export default function TermsPage() {
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
        <h1 className="text-3xl font-bold text-white mb-2">Terms of Service</h1>
        <p className="text-gray-400 mb-8">Last updated: January 2026</p>

        <div className="prose prose-invert prose-gray max-w-none space-y-8">
          <section>
            <h2 className="text-xl font-semibold text-white mb-4">1. Acceptance of Terms</h2>
            <p className="text-gray-300">
              By accessing or using RLCoach (&quot;the Service&quot;), you agree to be bound by these
              Terms of Service. If you do not agree to these terms, please do not use the Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">2. Description of Service</h2>
            <p className="text-gray-300">
              RLCoach provides Rocket League replay analysis and AI-powered coaching services.
              The Service includes:
            </p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>Replay file upload and processing</li>
              <li>Statistical analysis and visualization</li>
              <li>AI coaching powered by Claude (Pro subscription)</li>
              <li>Performance tracking over time</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">3. User Accounts</h2>
            <p className="text-gray-300">
              To use certain features, you must create an account via OAuth (Discord or Google).
              You are responsible for maintaining the security of your account and all activities
              that occur under it.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">4. Subscription and Payments</h2>
            <p className="text-gray-300">
              The Pro subscription is billed monthly at $10/month. You can cancel at any time
              through your account settings or Stripe billing portal. Your Pro features remain
              active until the end of the current billing period.
            </p>
            <p className="text-gray-300 mt-2">
              All payments are processed by Stripe. We do not store your payment card details.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">5. Acceptable Use</h2>
            <p className="text-gray-300">You agree not to:</p>
            <ul className="list-disc list-inside text-gray-300 mt-2 space-y-1">
              <li>Upload malicious files or attempt to exploit the Service</li>
              <li>Use the Service for any unlawful purpose</li>
              <li>Attempt to access other users&apos; data</li>
              <li>Resell or redistribute the Service without permission</li>
              <li>Interfere with the proper functioning of the Service</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">6. Intellectual Property</h2>
            <p className="text-gray-300">
              You retain ownership of your replay files. By uploading replays, you grant us a
              license to process and analyze them for the purpose of providing the Service.
              We may use anonymized, aggregated data for improving our services and benchmarks.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">7. Data and Privacy</h2>
            <p className="text-gray-300">
              Your use of the Service is also governed by our{' '}
              <Link href="/privacy" className="text-orange-500 hover:underline">
                Privacy Policy
              </Link>
              . We take data protection seriously and comply with GDPR requirements.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">8. Disclaimer of Warranties</h2>
            <p className="text-gray-300">
              THE SERVICE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTIES OF ANY KIND. We do not guarantee
              that the Service will be error-free or uninterrupted. AI coaching advice is for
              informational purposes only.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">9. Limitation of Liability</h2>
            <p className="text-gray-300">
              To the maximum extent permitted by law, RLCoach shall not be liable for any
              indirect, incidental, special, consequential, or punitive damages arising from
              your use of the Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">10. Account Termination</h2>
            <p className="text-gray-300">
              We may terminate or suspend your account for violations of these Terms. You may
              delete your account at any time through the Settings page. Account deletion
              requests have a 30-day grace period during which you can cancel.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">11. Changes to Terms</h2>
            <p className="text-gray-300">
              We may update these Terms from time to time. Continued use of the Service after
              changes constitutes acceptance of the new Terms. We will notify users of material
              changes via email or in-app notification.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-4">12. Contact</h2>
            <p className="text-gray-300">
              For questions about these Terms, contact us at{' '}
              <a href="mailto:legal@rlcoach.gg" className="text-orange-500 hover:underline">
                legal@rlcoach.gg
              </a>
            </p>
          </section>
        </div>

        {/* Footer */}
        <div className="mt-12 pt-8 border-t border-gray-800 text-center text-gray-500 text-sm">
          <p>
            <Link href="/privacy" className="hover:text-orange-500 transition-colors">
              Privacy Policy
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
