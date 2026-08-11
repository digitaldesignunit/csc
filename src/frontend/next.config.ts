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
};

export default nextConfig;
