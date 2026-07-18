/**
 * Next.js middleware for authentication.
 *
 * Protects routes that require authentication by redirecting
 * unauthenticated users to the login page.
 */

import { auth } from '@/lib/auth';
import { NextResponse } from 'next/server';

const protectedRoutes = [
  '/dashboard',
  '/replays',
  '/sessions',
  '/coach',
  '/settings',
  '/profile',
];

// Note: /coach allows free preview (1 message) so it's handled by the backend
const proRoutes: string[] = [];

export default auth((req) => {
  const { nextUrl } = req;
  const isLoggedIn = !!req.auth;

  const isProtectedRoute = protectedRoutes.some(
    (route) =>
      nextUrl.pathname === route || nextUrl.pathname.startsWith(`${route}/`)
  );

  const isProRoute = proRoutes.some(
    (route) =>
      nextUrl.pathname === route || nextUrl.pathname.startsWith(`${route}/`)
  );

  if (isProtectedRoute && !isLoggedIn) {
    const loginUrl = new URL('/login', nextUrl.origin);
    loginUrl.searchParams.set('callbackUrl', `${nextUrl.pathname}${nextUrl.search}`);
    return NextResponse.redirect(loginUrl);
  }

  if (isProRoute && isLoggedIn) {
    const tier = req.auth?.user?.subscriptionTier;
    if (tier !== 'pro') {
      return NextResponse.redirect(new URL('/upgrade', nextUrl.origin));
    }
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - api/auth (auth API routes)
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - public files
     */
    '/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\..*$).*)',
  ],
};
