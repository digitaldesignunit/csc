import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produce a self-contained server tree for CI → Uberspace deploys
  // (avoids running `next build` on hosts with an older glibc).
  output: "standalone",
  // Trace from the frontend itself: keeps `.next/standalone` flat (server.js at
  // its root) and silences the multi-lockfile root inference warning.
  outputFileTracingRoot: __dirname,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'public.ddu.uber.space',
        pathname: '/csc_assets/**',
      },
    ],
    // Disable image optimization for local development and problematic images
    unoptimized: process.env.NODE_ENV === 'development',
  },
  // `2ndchances.build` is the canonical origin. NextAuth v4 anchors every
  // absolute auth URL to the single `NEXTAUTH_URL`, so the legacy host cannot
  // serve the app itself — signing in there would set a host-only cookie and
  // then redirect to the canonical origin without it. Kept temporary (307)
  // until the switch has settled; browsers cache a 308 very aggressively.
  async redirects() {
    return [
      {
        source: '/:path*',
        has: [{ type: 'host', value: 'ddu.uber.space' }],
        destination: 'https://2ndchances.build/:path*',
        permanent: false,
      },
    ]
  },
};

export default nextConfig;
