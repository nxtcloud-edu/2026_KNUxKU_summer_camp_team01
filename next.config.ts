import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ['lucide-react'],
  },
  async redirects() {
    return [{ source: '/plan', destination: '/plan/new', permanent: false }];
  },
};

export default nextConfig;
