import NextAuth from 'next-auth';
import type { NextAuthConfig } from 'next-auth';
import Discord from 'next-auth/providers/discord';
import Google from 'next-auth/providers/google';
import type { JWT } from 'next-auth/jwt';

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

export const authConfig: NextAuthConfig = {
  providers: [
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
      // Initial sign in
      if (user) {
        token.userId = user.id!;
        token.subscriptionTier = user.subscriptionTier || 'free';
      }

      // Refresh subscription tier from database on session update
      if (trigger === 'update') {
        // Fetch fresh subscription status from API
        try {
          const res = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/api/v1/users/${token.userId}/subscription`,
            {
              headers: {
                Authorization: `Bearer ${token.accessToken}`,
              },
            }
          );
          if (res.ok) {
            const data = await res.json();
            token.subscriptionTier = data.tier;
          }
        } catch {
          // Keep existing tier on error
        }
      }

      return token;
    },
    async session({ session, token }) {
      session.user.id = token.userId;
      session.user.subscriptionTier = token.subscriptionTier;
      return session;
    },
    async signIn({ user, account, profile }) {
      // Allow all sign-ins by default
      // Could add logic here to block certain users or require email verification
      return true;
    },
  },
  events: {
    async signIn({ user, account, profile, isNewUser }) {
      if (isNewUser) {
        // New user created - could trigger welcome email or analytics
        console.log(`New user signed up: ${user.id}`);
      }
    },
  },
  debug: process.env.NODE_ENV === 'development',
};

export const { handlers, signIn, signOut, auth } = NextAuth(authConfig);
