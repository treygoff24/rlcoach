// frontend/src/app/api/auth/[...nextauth]/route.ts
/**
 * NextAuth.js API route handler.
 *
 * Exports GET and POST handlers that NextAuth uses for:
 * - OAuth callback handling (GET)
 * - Sign in/out requests (POST)
 * - Session management
 */

import { handlers } from '@/lib/auth';

export const { GET, POST } = handlers;
