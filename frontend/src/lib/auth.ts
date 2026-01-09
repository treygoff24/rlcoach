import NextAuth from 'next-auth';
import type { NextAuthConfig } from 'next-auth';
import Discord from 'next-auth/providers/discord';
import Google from 'next-auth/providers/google';
import Credentials from 'next-auth/providers/credentials';
import type { JWT } from 'next-auth/jwt';
import * as jose from 'jose';

const IS_DEV = process.env.NODE_ENV === 'development';

// Note: NEXTAUTH_SECRET validation happens at runtime in callbacks
// Build-time checks would fail since env vars aren't available during static analysis

/**
 * NextAuth configuration for rlcoach.
 *
 * Providers:
 * - Discord: Primary (where RL community lives)
 * - Google: Convenience fallback
 * - Steam: Via custom provider (see below)
 *
 * Session strategy: JWT (short-lived, 15 min)
 * Token includes: userId, email, subscriptionTier
 */

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      email?: string | null;
      name?: string | null;
      image?: string | null;
      subscriptionTier: 'free' | 'pro';
    };
    accessToken?: string;
  }

  interface User {
    subscriptionTier?: 'free' | 'pro';
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    userId: string;
    subscriptionTier: 'free' | 'pro';
    accessToken?: string;
  }
}

// Steam OpenID provider (custom implementation)
const Steam = {
  id: 'steam',
  name: 'Steam',
  type: 'oauth' as const,
  authorization: {
    url: 'https://steamcommunity.com/openid/login',
    params: {
      'openid.ns': 'http://specs.openid.net/auth/2.0',
      'openid.mode': 'checkid_setup',
      'openid.return_to': `${process.env.NEXTAUTH_URL}/api/auth/callback/steam`,
      'openid.realm': process.env.NEXTAUTH_URL,
      'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
      'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
    },
  },
  token: {
    url: '', // Steam uses OpenID, not OAuth tokens
  },
  userinfo: {
    url: 'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/',
    async request({ tokens, provider }: { tokens: any; provider: any }) {
      // Extract Steam ID from the claimed_id response
      const steamId = tokens.id?.match(/\d+$/)?.[0];
      if (!steamId) return null;

      const res = await fetch(
        `https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key=${process.env.STEAM_API_KEY}&steamids=${steamId}`
      );
      const data = await res.json();
      const player = data.response?.players?.[0];

      return {
        id: steamId,
        name: player?.personaname,
        image: player?.avatarfull,
      };
    },
  },
  profile(profile: any) {
    return {
      id: profile.id,
      name: profile.name,
      image: profile.image,
    };
  },
};

// Backend URL for server-side calls during auth
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// Dev-only mock user for local testing
const DevCredentials = Credentials({
  id: 'dev-login',
  name: 'Dev Login',
  credentials: {},
  async authorize() {
    if (!IS_DEV) return null;
    return {
      id: 'dev-user-123',
      name: 'Dev User',
      email: 'dev@localhost',
      subscriptionTier: 'pro' as const,
    };
  },
});

export const authConfig: NextAuthConfig = {
  providers: [
    // Dev login - only works in development
    ...(IS_DEV ? [DevCredentials] : []),
    Discord({
      clientId: process.env.DISCORD_CLIENT_ID!,
      clientSecret: process.env.DISCORD_CLIENT_SECRET!,
    }),
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    // Steam provider disabled until we implement proper OpenID handling
    // Steam,
  ],
  pages: {
    signIn: '/login',
    error: '/login',
  },
  session: {
    strategy: 'jwt',
    maxAge: 15 * 60, // 15 minutes (short-lived for security)
  },
  callbacks: {
    async jwt({ token, user, account, trigger }) {
      // Initial sign in - bootstrap user in our database
      if (account && user) {
        try {
          // Compute HMAC signature for bootstrap request
          const crypto = await import('crypto');
          const bootstrapSecret = process.env.BOOTSTRAP_SECRET || '';
          const payload = `${account.provider}:${account.providerAccountId}:${user.email || ''}`;
          const signature = bootstrapSecret
            ? crypto.createHmac('sha256', bootstrapSecret).update(payload).digest('hex')
            : '';

          // Call our backend to create/find the user
          const res = await fetch(`${BACKEND_URL}/api/v1/users/bootstrap`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(signature && { 'X-Bootstrap-Signature': signature }),
            },
            body: JSON.stringify({
              provider: account.provider,
              provider_account_id: account.providerAccountId,
              email: user.email,
              name: user.name,
              image: user.image,
            }),
          });

          if (res.ok) {
            const data = await res.json();
            // Use our database UUID, not the OAuth provider's ID
            token.userId = data.id;
            token.subscriptionTier = data.subscription_tier || 'free';
          } else {
            // Fallback to OAuth ID if bootstrap fails
            console.error('User bootstrap failed:', await res.text());
            token.userId = user.id!;
            token.subscriptionTier = 'free';
          }
        } catch (error) {
          // Fallback to OAuth ID if bootstrap fails
          console.error('User bootstrap error:', error);
          token.userId = user.id!;
          token.subscriptionTier = 'free';
        }
      }

      return token;
    },
    async session({ session, token }) {
      session.user.id = token.userId;
      session.user.subscriptionTier = token.subscriptionTier;

      // Create a signed JWT for backend API calls
      // Backend expects JWT with userId/sub signed with NEXTAUTH_SECRET
      const secretStr = process.env.NEXTAUTH_SECRET;
      if (secretStr) {
        const secret = new TextEncoder().encode(secretStr);
        const jwt = await new jose.SignJWT({
          userId: token.userId,
          sub: token.userId,
          email: token.email,
          subscriptionTier: token.subscriptionTier,
        })
          .setProtectedHeader({ alg: 'HS256' })
          .setExpirationTime('15m')
          .sign(secret);

        session.accessToken = jwt;
      }
      // If no secret, accessToken stays undefined (API calls will fail with auth error)
      return session;
    },
    async signIn({ user, account, profile }) {
      // Allow all sign-ins by default
      // Bootstrap happens in jwt callback
      return true;
    },
  },
  events: {
    async signIn({ user, account, profile, isNewUser }) {
      if (isNewUser) {
        console.log(`New OAuth sign-in: ${account?.provider} - ${user.id}`);
      }
    },
  },
  debug: process.env.NODE_ENV === 'development',
};

export const { handlers, signIn, signOut, auth } = NextAuth(authConfig);
