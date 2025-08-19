import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'public.ddu.uber.space',
        pathname: '**',
      },
      {
        protocol: 'https',
        hostname: 'https://public.ddu.uber.space/csc_assets/component_preview',
        pathname: '**',
      },
      {
        protocol: 'https',
        hostname: 'https://public.ddu.uber.space/csc_assets/component_geometry',
        pathname: '**',
      },
    ],
  },
};

export default nextConfig;
