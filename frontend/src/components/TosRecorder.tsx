/**
 * TosRecorder - Records ToS acceptance after OAuth sign-in.
 *
 * Checks sessionStorage for tos_accepted_at (set by login page).
 * If present, calls API to record acceptance and clears storage.
 * Silent component - no UI rendered.
 */

'use client';

import { useSession } from 'next-auth/react';
import { useEffect, useRef } from 'react';

export function TosRecorder() {
  const { data: session, status } = useSession();
  const recordedRef = useRef(false);

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
        }
      })
      .catch((err) => {
        // Log but don't fail - ToS was already accepted in UI
        console.error('Failed to record ToS acceptance:', err);
      });
  }, [session, status]);

  // This component renders nothing
  return null;
}
