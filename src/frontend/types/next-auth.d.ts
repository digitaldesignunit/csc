import NextAuth, { DefaultSession } from 'next-auth';

declare module 'next-auth/jwt' {
  interface JWT {
    role?: string;
    username?: string;
    apiToken?: string;         // FastAPI token (server-only)
    apiTokenIssuedAt?: number;
  }
}

declare module 'next-auth' {
  interface Session {
    user: {
      id?: string;
      role?: string;
      username?: string;
    } & DefaultSession['user'];
  }
}
