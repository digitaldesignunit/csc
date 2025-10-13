import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
