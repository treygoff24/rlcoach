/**
 * TosRecorder - Records ToS acceptance after OAuth sign-in.
 *
 * Checks sessionStorage for tos_accepted_at (set by login page).
 * If present, calls API to record acceptance and clears storage.
 * Silent component - no UI rendered.
 */

'use client';

import { useSession } from 'next-auth/react';
import { useEffect, useRef, useState } from 'react';

export function TosRecorder() {
  const { data: session, status } = useSession();
  const recordedRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    // Only run once per session when authenticated
    if (status !== 'authenticated' || !session?.user || recordedRef.current) {
      return;
    }

    const acceptedAt = sessionStorage.getItem('tos_accepted_at');
    if (!acceptedAt) {
      return;
    }

    // Mark as recorded to prevent duplicate calls
    recordedRef.current = true;

    // Record acceptance via API
    fetch('/api/v1/users/me/accept-tos', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ accepted_at: acceptedAt }),
    })
      .then((res) => {
        if (res.ok) {
          // Clear storage on success
          sessionStorage.removeItem('tos_accepted_at');
          return;
        }
        recordedRef.current = false;
        throw new Error('Failed to record ToS acceptance');
      })
      .catch((err) => {
        recordedRef.current = false;
        if (!retryTimerRef.current) {
          retryTimerRef.current = setTimeout(() => {
            retryTimerRef.current = null;
            setRetryToken((token) => token + 1);
          }, 5000);
        }
        console.error('Failed to record ToS acceptance:', err);
      });
  }, [session, status, retryToken]);

  // This component renders nothing
  return null;
}
