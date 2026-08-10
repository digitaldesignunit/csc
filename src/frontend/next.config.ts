import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Produce a self-contained server tree for CI → Uberspace deploys
  // (avoids running `next build` on hosts with an older glibc).
  output: "standalone",
  // Repo root is two levels up from src/frontend (silences multi-lockfile warning).
  outputFileTracingRoot: path.join(__dirname, "../.."),
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
