// frontend/src/app/(dashboard)/coach/page.tsx
'use client';

import { useState, useRef, useEffect } from 'react';
import { useSession } from 'next-auth/react';
import Link from 'next/link';
import { useASPStream } from '@/components/coach/stream/useASPStream';


export default function CoachPage() {
  const { data: session } = useSession();
  const { state, handleEvent } = useASPStream();
  const messages = state.messages;
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [budgetRemaining, setBudgetRemaining] = useState<number>(150000);
  const [error, setError] = useState<string | null>(null);
  const [freePreviewUsed, setFreePreviewUsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const streamError = state.error;
  const displayError = error || streamError;

  const user = session?.user as { subscriptionTier?: string } | undefined;
  const isPro = user?.subscriptionTier === 'pro';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, state.thinking, state.toolStatus]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userText = input.trim();
    handleEvent({ type: 'user_message', text: userText });
    setInput('');
    setIsLoading(true);
    setError(null);
    setShowThinking(false);

    try {
      const response = await fetch('/api/coach/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        if (response.status === 402) {
          setFreePreviewUsed(true);
          setError(err.detail || err.error || 'Upgrade to Pro for unlimited coaching.');
          return;
        }
        throw new Error(err.detail || err.error || 'Failed to send message');
      }

      if (!response.body) {
        throw new Error('No stream available');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          const payload = line.replace(/^data:\s*/, '');
          if (!payload) continue;

          const event = JSON.parse(payload);
          if (event.type === 'ack') {
            if (event.session_id) {
              setSessionId(event.session_id);
            }
            if (event.budget_remaining !== undefined) {
              setBudgetRemaining(event.budget_remaining);
            }
            if (event.is_free_preview) {
              setFreePreviewUsed(true);
            }
            continue;
          }

          handleEvent(event);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDismissError = () => {
    setError(null);
    inputRef.current?.focus();
  };

  // Free tier intro - show this before they've sent any messages
  if (!isPro && messages.length === 0) {
    return (
      <div className="flex flex-col h-[calc(100vh-4rem)]">
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">AI Coach</h1>
              <p className="text-sm text-gray-400">Powered by Claude Opus 4.5</p>
            </div>
          </div>
        </div>

        {/* Free preview intro */}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center max-w-lg">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-orange-500/20 to-orange-600/20 flex items-center justify-center">
              <svg className="w-10 h-10 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">Try the AI Coach</h2>
            <p className="text-gray-400 mb-6">
              Get a taste of personalized coaching from Claude Opus 4.5 with extended thinking.
              Ask about your gameplay, weaknesses, or how to improve.
            </p>
            <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4 mb-6">
              <p className="text-orange-400 text-sm font-medium">
                You have 1 free message to try the coach
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 mb-8">
              {[
                'What should I focus on to rank up?',
                'How can I improve my boost management?',
                'Review my recent gameplay patterns',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white transition-colors text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Input */}
        <div className="flex-shrink-0 p-4 border-t border-gray-800 pb-safe">
          <div className="flex gap-3">
            <label htmlFor="coach-input" className="sr-only">
              Ask your AI coach
            </label>
            <input
              ref={inputRef}
              id="coach-input"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask your AI coach..."
              disabled={isLoading}
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent disabled:opacity-50"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              aria-label="Send message"
              className="px-6 py-3 bg-orange-500 text-white font-medium rounded-xl hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">AI Coach</h1>
              <p className="text-sm text-gray-400">Powered by Claude Opus 4.5</p>
            </div>
          </div>
          {isPro && (
            <div className="text-right">
              <p className="text-sm text-gray-400">Token Budget</p>
              <p className="text-sm font-medium text-white">
                {budgetRemaining.toLocaleString()} / 150,000
              </p>
            </div>
          )}
          {!isPro && freePreviewUsed && (
            <Link
              href="/upgrade"
              className="px-4 py-2 bg-orange-500 text-white text-sm font-medium rounded-lg hover:bg-orange-600 transition-colors"
            >
              Upgrade to Pro
            </Link>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6" role="log" aria-label="Chat messages" aria-live="polite">
        {messages.length === 0 && isPro && (
          <div className="text-center py-16">
            <p className="text-gray-400 mb-6">
              Ask me anything about your gameplay. I can analyze your replays,
              identify patterns, and give you specific tips to improve.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {[
                'Review my last session',
                'What should I focus on?',
                'How is my boost management?',
                'Compare me to my rank',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white transition-colors text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] ${
                message.role === 'user'
                  ? 'bg-orange-500 text-white rounded-2xl rounded-tr-sm'
                  : 'bg-gray-800 text-gray-100 rounded-2xl rounded-tl-sm'
              } px-4 py-3`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ))}

        {state.toolStatus && (
          <div className="flex justify-start">
            <div className="bg-gray-800 text-gray-300 rounded-2xl rounded-tl-sm px-4 py-2 text-xs">
              {state.toolStatus}
            </div>
          </div>
        )}

        {state.thinking && (
          <div className="flex justify-start">
            <div className="bg-gray-900/50 border border-gray-700 rounded-xl px-4 py-3 max-w-[80%]">
              <button
                onClick={() => setShowThinking(!showThinking)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-300 mb-2"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                {showThinking ? 'Hide thinking' : 'Show thinking'}
              </button>
              {showThinking && (
                <p className="text-xs text-gray-400 whitespace-pre-wrap">{state.thinking}</p>
              )}
            </div>
          </div>
        )}

        {/* Free preview upgrade prompt - show after their free message */}
        {!isPro && freePreviewUsed && messages.length > 0 && !isLoading && !displayError && (
          <div className="flex justify-center py-4">
            <div className="bg-gradient-to-r from-orange-500/10 to-orange-600/10 border border-orange-500/30 rounded-xl p-6 max-w-md text-center">
              <h3 className="text-lg font-semibold text-white mb-2">
                Ready for more coaching?
              </h3>
              <p className="text-gray-400 text-sm mb-4">
                Upgrade to Pro for unlimited AI coaching, extended thinking analysis,
                and personalized improvement plans.
              </p>
              <Link
                href="/upgrade"
                className="inline-block px-6 py-3 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 transition-colors"
              >
                Upgrade to Pro - $10/month
              </Link>
            </div>
          </div>
        )}

        {isLoading && (
          <div className="flex justify-start" role="status" aria-label="AI is thinking">
            <div className="bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-orange-500 animate-bounce" style={{ animationDelay: '0ms' }} aria-hidden="true" />
                <div className="w-2 h-2 rounded-full bg-orange-500 animate-bounce" style={{ animationDelay: '150ms' }} aria-hidden="true" />
                <div className="w-2 h-2 rounded-full bg-orange-500 animate-bounce" style={{ animationDelay: '300ms' }} aria-hidden="true" />
              </div>
              <span className="sr-only">AI coach is thinking...</span>
            </div>
          </div>
        )}

        {displayError && (
          <div className="flex justify-center" role="alert">
            <div className="bg-red-500/20 border border-red-500/50 rounded-lg px-4 py-3 flex items-center gap-3">
              <span className="text-red-400 text-sm">{displayError}</span>
              <button
                onClick={handleDismissError}
                className="text-red-400 hover:text-red-300 text-sm underline focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input - disabled for free users who have used their preview */}
      <div className="flex-shrink-0 p-4 border-t border-gray-800 pb-safe">
        {!isPro && freePreviewUsed ? (
          <div className="text-center py-2">
            <p className="text-gray-400 text-sm mb-3">
              You've used your free preview message.
            </p>
            <Link
              href="/upgrade"
              className="inline-flex items-center gap-2 px-4 py-2 bg-orange-500 text-white text-sm font-medium rounded-lg hover:bg-orange-600 transition-colors"
            >
              Upgrade to continue chatting
            </Link>
          </div>
        ) : (
          <div className="flex gap-3">
            <label htmlFor="coach-input" className="sr-only">
              Ask your AI coach
            </label>
            <input
              ref={inputRef}
              id="coach-input"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask your AI coach..."
              disabled={isLoading}
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent disabled:opacity-50"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              aria-label="Send message"
              className="px-6 py-3 bg-orange-500 text-white font-medium rounded-xl hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
