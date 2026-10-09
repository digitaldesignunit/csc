import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A second dev server for browser checks (`invoke dev-migrated` plus a
  // frontend on another port) needs a build folder of its own: Next allows
  // one dev server per folder. Unset, this is `.next` as always.
  distDir: process.env.NEXT_DIST_DIR || '.next',
  // Produce a self-contained server tree for CI --> Uberspace deploys
  // (avoids running `next build` on hosts with an older glibc).
  output: "standalone",
  // Trace from the frontend itself: keeps `.next/standalone` flat (server.js at
  // its root) and silences the multi-lockfile root inference warning.
  outputFileTracingRoot: __dirname,
  // Browser checks on 127.0.0.1 (a cookie jar of its own, apart from other
  // apps on localhost) need the dev server to accept that origin.
  allowedDevOrigins: ['127.0.0.1'],
  // Evidence attachments (a lab report as a PDF) reach the backend through
  // the /api/backend proxy, whose request bodies the proxy step buffers;
  // the default 10 MB would cut a larger upload. A file is capped at 25 MB
  // (decision 8.82) and the backend answers 413; this is that plus the
  // multipart overhead.
  experimental: {
    proxyClientMaxBodySize: '26mb',
  },
  images: {
    // No remote image host: catalogue files (previews, photos, meshes,
    // proxies, capture fixtures) are never fetched from a static host. They
    // come through the authenticated /snapshots/... routes of the API
    // (decision 8.125 a), which serve public pieces to anonymous callers too.
    // Disable image optimization for local development and problematic images
    unoptimized: process.env.NODE_ENV === 'development',
  },
  // `2ndchances.build` is the canonical origin. NextAuth v4 anchors every
  // absolute auth URL to the single `NEXTAUTH_URL`, so the legacy host cannot
  // serve the app itself --- signing in there would set a host-only cookie and
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
