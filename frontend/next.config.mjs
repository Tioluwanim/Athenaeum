/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // react-pdf needs canvas to be treated as external in the browser bundle
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;
