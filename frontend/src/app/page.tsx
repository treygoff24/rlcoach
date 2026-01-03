import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold gradient-text">rlcoach</span>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="/api/auth/signin" className="btn-secondary">
              Sign In
            </Link>
            <Link href="/api/auth/signin" className="btn-primary">
              Get Started
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="py-20 text-center">
          <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">
            The Best <span className="gradient-text">AI Coach</span>
            <br />
            for Rocket League
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-400">
            Upload your replays, get detailed analytics, and receive personalized
            coaching from Claude Opus 4.5. Improve faster than ever.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link href="/api/auth/signin" className="btn-primary px-8 py-3 text-lg">
              Start Free
            </Link>
            <Link href="#features" className="btn-secondary px-8 py-3 text-lg">
              Learn More
            </Link>
          </div>
        </div>

        {/* Features Section */}
        <section id="features" className="py-20">
          <h2 className="text-center text-3xl font-bold">
            Everything You Need to Improve
          </h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            <FeatureCard
              title="Detailed Analytics"
              description="Track every mechanic, boost pickup, and positioning decision across all your games."
              icon="chart"
            />
            <FeatureCard
              title="AI Coaching"
              description="Get personalized feedback from Claude Opus 4.5 with extended thinking capabilities."
              icon="brain"
            />
            <FeatureCard
              title="Progress Tracking"
              description="See your improvement over time with beautiful visualizations and trend analysis."
              icon="trending"
            />
          </div>
        </section>

        {/* Pricing Section */}
        <section className="py-20">
          <h2 className="text-center text-3xl font-bold">Simple Pricing</h2>
          <div className="mt-12 grid gap-8 md:grid-cols-2 max-w-4xl mx-auto">
            <div className="card">
              <h3 className="text-xl font-bold">Free</h3>
              <p className="mt-2 text-4xl font-bold">$0</p>
              <p className="text-gray-400">Forever</p>
              <ul className="mt-6 space-y-3 text-gray-300">
                <li>Unlimited replay uploads</li>
                <li>Full dashboard access</li>
                <li>All analytics features</li>
                <li>Trend tracking</li>
              </ul>
              <Link href="/api/auth/signin" className="btn-secondary mt-8 w-full">
                Get Started
              </Link>
            </div>
            <div className="card border-brand-500 relative">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-500 px-3 py-1 text-sm font-medium">
                Recommended
              </div>
              <h3 className="text-xl font-bold">Pro</h3>
              <p className="mt-2 text-4xl font-bold">$10</p>
              <p className="text-gray-400">per month</p>
              <ul className="mt-6 space-y-3 text-gray-300">
                <li>Everything in Free</li>
                <li>AI coach powered by Claude</li>
                <li>Extended thinking analysis</li>
                <li>Personalized improvement plans</li>
                <li>Session notes & tracking</li>
              </ul>
              <Link href="/api/auth/signin" className="btn-primary mt-8 w-full">
                Upgrade to Pro
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-8">
        <div className="mx-auto max-w-7xl px-4 text-center text-sm text-gray-400">
          <p>&copy; {new Date().getFullYear()} rlcoach. All rights reserved.</p>
          <div className="mt-4 flex justify-center gap-6">
            <Link href="/terms" className="hover:text-white">
              Terms of Service
            </Link>
            <Link href="/privacy" className="hover:text-white">
              Privacy Policy
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: 'chart' | 'brain' | 'trending';
}) {
  return (
    <div className="card text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/20 text-brand-400">
        {icon === 'chart' && (
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        )}
        {icon === 'brain' && (
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        )}
        {icon === 'trending' && (
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
        )}
      </div>
      <h3 className="text-xl font-semibold">{title}</h3>
      <p className="mt-2 text-gray-400">{description}</p>
    </div>
  );
}
