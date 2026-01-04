// frontend/src/app/page.tsx
import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-gray-800/50 bg-gray-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold gradient-text">rlcoach</span>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="#features" className="hidden sm:block text-gray-400 hover:text-white transition-colors">
              Features
            </Link>
            <Link href="#pricing" className="hidden sm:block text-gray-400 hover:text-white transition-colors">
              Pricing
            </Link>
            <Link href="/login" className="btn-secondary">
              Sign In
            </Link>
            <Link href="/login" className="btn-primary">
              Get Started
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <main className="pt-16">
        <section className="relative overflow-hidden">
          {/* Background gradient orbs */}
          <div className="absolute top-20 left-1/4 w-96 h-96 bg-orange-500/10 rounded-full blur-3xl" />
          <div className="absolute top-40 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />

          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative">
            <div className="py-24 lg:py-32 text-center">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-orange-500/10 border border-orange-500/20 text-orange-400 text-sm mb-8">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-orange-500" />
                </span>
                Powered by Claude Opus 4.5 with Extended Thinking
              </div>

              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight">
                Your Personal
                <br />
                <span className="gradient-text">AI Rocket League Coach</span>
              </h1>

              <p className="mx-auto mt-6 max-w-2xl text-lg lg:text-xl text-gray-400">
                Upload replays. Get instant analytics. Receive personalized coaching
                from the most advanced AI available. Rank up faster than ever.
              </p>

              <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
                <Link href="/login" className="btn-primary px-8 py-4 text-lg w-full sm:w-auto">
                  Start Free — No Credit Card
                </Link>
                <Link href="#how-it-works" className="btn-secondary px-8 py-4 text-lg w-full sm:w-auto">
                  See How It Works
                </Link>
              </div>

              <p className="mt-6 text-sm text-gray-500">
                Join 2,000+ players improving their game
              </p>
            </div>
          </div>
        </section>

        {/* Stats Banner */}
        <section className="border-y border-gray-800 bg-gray-900/50">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 text-center">
              <div>
                <p className="text-3xl lg:text-4xl font-bold gradient-text">50K+</p>
                <p className="mt-1 text-sm text-gray-400">Replays Analyzed</p>
              </div>
              <div>
                <p className="text-3xl lg:text-4xl font-bold gradient-text">98%</p>
                <p className="mt-1 text-sm text-gray-400">Accuracy Rate</p>
              </div>
              <div>
                <p className="text-3xl lg:text-4xl font-bold gradient-text">2.5K+</p>
                <p className="mt-1 text-sm text-gray-400">Active Players</p>
              </div>
              <div>
                <p className="text-3xl lg:text-4xl font-bold gradient-text">300+</p>
                <p className="mt-1 text-sm text-gray-400">Rank-Ups Reported</p>
              </div>
            </div>
          </div>
        </section>

        {/* How It Works */}
        <section id="how-it-works" className="py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-16">
              <h2 className="text-3xl lg:text-4xl font-bold">
                How It Works
              </h2>
              <p className="mt-4 text-gray-400 max-w-2xl mx-auto">
                Get from replay to actionable insights in under a minute
              </p>
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
              <StepCard
                number={1}
                title="Upload Your Replay"
                description="Drag and drop your .replay file. We support all game modes and playlists."
              />
              <StepCard
                number={2}
                title="Get Instant Analysis"
                description="See your boost usage, positioning, mechanics, and more — broken down by moment."
              />
              <StepCard
                number={3}
                title="Ask Your AI Coach"
                description="Get personalized tips from Claude. Ask anything about your gameplay."
              />
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section id="features" className="py-24 bg-gray-900/30">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-16">
              <h2 className="text-3xl lg:text-4xl font-bold">
                Everything You Need to Improve
              </h2>
              <p className="mt-4 text-gray-400 max-w-2xl mx-auto">
                Comprehensive analytics and AI coaching in one place
              </p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              <FeatureCard
                title="Mechanic Detection"
                description="Track flip resets, wavedashes, speed flips, ceiling shots, and 15+ other mechanics automatically."
                icon="mechanic"
              />
              <FeatureCard
                title="Boost Analytics"
                description="See your boost efficiency, pad collection patterns, and starve opportunities."
                icon="boost"
              />
              <FeatureCard
                title="Positioning Heatmaps"
                description="Visualize where you spend time on the field compared to your rank peers."
                icon="heatmap"
              />
              <FeatureCard
                title="Session Trends"
                description="Group replays into sessions and track your performance over time."
                icon="trending"
              />
              <FeatureCard
                title="AI Coaching"
                description="Ask Claude Opus 4.5 anything about your gameplay. Get extended-thinking analysis."
                icon="brain"
              />
              <FeatureCard
                title="Team Analysis"
                description="See rotation patterns, passing plays, and team chemistry metrics."
                icon="team"
              />
            </div>
          </div>
        </section>

        {/* AI Coach Highlight */}
        <section className="py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="grid lg:grid-cols-2 gap-12 items-center">
              <div>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-500/10 border border-orange-500/20 text-orange-400 text-sm mb-6">
                  Pro Feature
                </div>
                <h2 className="text-3xl lg:text-4xl font-bold mb-6">
                  AI Coaching That Actually Understands Your Game
                </h2>
                <p className="text-gray-400 text-lg mb-6">
                  Unlike generic advice, our AI coach has seen your actual replays.
                  It knows your boost habits, your rotation patterns, and exactly
                  where you can improve.
                </p>
                <ul className="space-y-4 text-gray-300">
                  <li className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Remembers context across sessions
                  </li>
                  <li className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Uses extended thinking for deep analysis
                  </li>
                  <li className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Creates personalized practice plans
                  </li>
                  <li className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Adapts advice to your skill level
                  </li>
                </ul>
                <Link href="/login" className="inline-flex btn-primary mt-8 px-6 py-3">
                  Try Your Free Coach Message
                </Link>
              </div>
              <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-orange-500/20 flex items-center justify-center">
                    <svg className="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-medium text-white">AI Coach</p>
                    <p className="text-xs text-gray-400">Powered by Claude Opus 4.5</p>
                  </div>
                </div>
                <div className="space-y-4 text-sm">
                  <div className="bg-gray-700/50 rounded-lg p-3">
                    <p className="text-gray-300">Looking at your last 5 games, I notice you're consistently running low on boost during defensive rotations. Here's what's happening...</p>
                  </div>
                  <div className="bg-gray-700/50 rounded-lg p-3">
                    <p className="text-gray-300">Your average boost when reaching the back post is 18. For comparison, Diamond players average 34. The issue starts at 0:45 when you...</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Pricing Section */}
        <section id="pricing" className="py-24 bg-gray-900/30">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-16">
              <h2 className="text-3xl lg:text-4xl font-bold">Simple, Transparent Pricing</h2>
              <p className="mt-4 text-gray-400 max-w-2xl mx-auto">
                Full analytics free forever. AI coaching when you're ready.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
              <div className="card">
                <h3 className="text-xl font-bold">Free</h3>
                <p className="mt-4">
                  <span className="text-4xl font-bold">$0</span>
                  <span className="text-gray-400 ml-2">forever</span>
                </p>
                <ul className="mt-8 space-y-4 text-gray-300">
                  <PricingFeature included>Unlimited replay uploads</PricingFeature>
                  <PricingFeature included>Full dashboard access</PricingFeature>
                  <PricingFeature included>All analytics features</PricingFeature>
                  <PricingFeature included>Session grouping</PricingFeature>
                  <PricingFeature included>Trend tracking</PricingFeature>
                  <PricingFeature included>One free AI coach message</PricingFeature>
                  <PricingFeature>Unlimited AI coaching</PricingFeature>
                  <PricingFeature>Personalized practice plans</PricingFeature>
                </ul>
                <Link href="/login" className="btn-secondary mt-8 w-full py-3">
                  Get Started Free
                </Link>
              </div>

              <div className="card border-orange-500/50 relative">
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-orange-500 px-4 py-1 text-sm font-medium">
                  Most Popular
                </div>
                <h3 className="text-xl font-bold">Pro</h3>
                <p className="mt-4">
                  <span className="text-4xl font-bold">$10</span>
                  <span className="text-gray-400 ml-2">/month</span>
                </p>
                <ul className="mt-8 space-y-4 text-gray-300">
                  <PricingFeature included>Everything in Free</PricingFeature>
                  <PricingFeature included>Unlimited AI coaching</PricingFeature>
                  <PricingFeature included>Extended thinking analysis</PricingFeature>
                  <PricingFeature included>Personalized practice plans</PricingFeature>
                  <PricingFeature included>Session notes & tracking</PricingFeature>
                  <PricingFeature included>Priority processing</PricingFeature>
                  <PricingFeature included>Early access to new features</PricingFeature>
                </ul>
                <Link href="/login" className="btn-primary mt-8 w-full py-3">
                  Start Pro Trial
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="py-24">
          <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
            <h2 className="text-3xl font-bold text-center mb-12">
              Frequently Asked Questions
            </h2>

            <div className="space-y-6">
              <FAQItem
                question="How do I get my replay files?"
                answer="Rocket League automatically saves replays. On PC, they're in Documents/My Games/Rocket League/TAGame/Demos. You can also save replays manually after a match."
              />
              <FAQItem
                question="What game modes are supported?"
                answer="All competitive and casual playlists are supported, including 1v1, 2v2, 3v3, and extra modes like Hoops and Rumble."
              />
              <FAQItem
                question="How accurate is the mechanic detection?"
                answer="Our detection uses physics-based analysis at 30Hz frame rate. We achieve 98%+ accuracy on common mechanics like aerials, flips, and wavedashes."
              />
              <FAQItem
                question="What makes the AI coach different from other tools?"
                answer="We use Claude Opus 4.5 with extended thinking, which means it can reason through complex gameplay scenarios. It also has access to all your replay data, so advice is based on your actual games."
              />
              <FAQItem
                question="Can I cancel my Pro subscription anytime?"
                answer="Yes, you can cancel anytime. Your Pro features remain active until the end of your billing period, then you'll automatically switch to Free."
              />
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-24 bg-gradient-to-b from-gray-900/50 to-gray-950">
          <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 text-center">
            <h2 className="text-3xl lg:text-4xl font-bold">
              Ready to Rank Up?
            </h2>
            <p className="mt-4 text-gray-400 text-lg max-w-2xl mx-auto">
              Join thousands of players who are improving faster with AI-powered coaching.
            </p>
            <Link href="/login" className="inline-flex btn-primary mt-8 px-10 py-4 text-lg">
              Get Started — It's Free
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold gradient-text">rlcoach</span>
            </div>
            <div className="flex items-center gap-8 text-sm text-gray-400">
              <Link href="/terms" className="hover:text-white transition-colors">
                Terms of Service
              </Link>
              <Link href="/privacy" className="hover:text-white transition-colors">
                Privacy Policy
              </Link>
              <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">
                GitHub
              </a>
              <a href="https://discord.gg" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">
                Discord
              </a>
            </div>
          </div>
          <p className="mt-8 text-center text-sm text-gray-500">
            &copy; {new Date().getFullYear()} rlcoach. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}

function StepCard({
  number,
  title,
  description,
}: {
  number: number;
  title: string;
  description: string;
}) {
  return (
    <div className="relative text-center">
      <div className="mx-auto w-16 h-16 rounded-full bg-orange-500/20 border-2 border-orange-500/40 flex items-center justify-center mb-6">
        <span className="text-2xl font-bold text-orange-400">{number}</span>
      </div>
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-gray-400">{description}</p>
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
  icon: 'mechanic' | 'boost' | 'heatmap' | 'trending' | 'brain' | 'team';
}) {
  const icons = {
    mechanic: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    boost: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
      </svg>
    ),
    heatmap: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
      </svg>
    ),
    trending: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
    brain: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
    team: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
  };

  return (
    <div className="card hover:border-gray-700 transition-colors">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-orange-500/20 text-orange-400">
        {icons[icon]}
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-gray-400 text-sm">{description}</p>
    </div>
  );
}

function PricingFeature({
  children,
  included = false,
}: {
  children: React.ReactNode;
  included?: boolean;
}) {
  return (
    <li className={`flex items-center gap-3 ${included ? '' : 'text-gray-500'}`}>
      {included ? (
        <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
        </svg>
      ) : (
        <svg className="w-5 h-5 text-gray-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      )}
      {children}
    </li>
  );
}

function FAQItem({
  question,
  answer,
}: {
  question: string;
  answer: string;
}) {
  return (
    <details className="group">
      <summary className="flex items-center justify-between cursor-pointer list-none p-4 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors">
        <span className="font-medium">{question}</span>
        <svg className="w-5 h-5 text-gray-400 group-open:rotate-180 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </summary>
      <p className="mt-2 px-4 pb-4 text-gray-400">
        {answer}
      </p>
    </details>
  );
}
