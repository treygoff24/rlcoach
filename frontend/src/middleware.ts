// frontend/src/middleware.ts
/**
 * Next.js middleware for authentication.
 *
 * Protects routes that require authentication by redirecting
 * unauthenticated users to the login page.
 */

import { auth } from '@/lib/auth';
import { NextResponse } from 'next/server';

// Routes that require authentication
const protectedRoutes = [
  '/dashboard',
  '/replays',
  '/coach',
  '/settings',
  '/profile',
];

// Routes that require Pro subscription
const proRoutes = ['/coach'];

export default auth((req) => {
  const { nextUrl } = req;
  const isLoggedIn = !!req.auth;

  // Check if path starts with any protected route
  const isProtectedRoute = protectedRoutes.some(
    (route) =>
      nextUrl.pathname === route || nextUrl.pathname.startsWith(`${route}/`)
  );

  const isProRoute = proRoutes.some(
    (route) =>
      nextUrl.pathname === route || nextUrl.pathname.startsWith(`${route}/`)
  );

  // Redirect unauthenticated users to login
  if (isProtectedRoute && !isLoggedIn) {
    const loginUrl = new URL('/login', nextUrl.origin);
    loginUrl.searchParams.set('callbackUrl', nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Check Pro subscription for coach routes
  if (isProRoute && isLoggedIn) {
    const tier = req.auth?.user?.subscriptionTier;
    if (tier !== 'pro') {
      return NextResponse.redirect(new URL('/upgrade', nextUrl.origin));
    }
  }

  return NextResponse.next();
});

// Configure which paths the middleware runs on
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
