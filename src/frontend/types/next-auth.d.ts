import { DefaultSession } from 'next-auth';

declare module 'next-auth/jwt' {
  interface JWT {
    role?: string;
    username?: string;
    apiToken?: string;         // FastAPI token (server-only)
    apiTokenExpiresAt?: number
    apiTokenIssuedAt?: number;
    error?: "ApiTokenExpired"
  }
}

declare module "next-auth" {
  interface Session {
    user: DefaultSession["user"] & {
      id?: string
      role?: string
      username?: string
    }
    api?: {
      hasAccessToken: boolean
      expiresAt: number
    }
    error?: "ApiTokenExpired"
  }
}