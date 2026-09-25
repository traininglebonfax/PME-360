import type { NextConfig } from "next";

// L'API Django est servie derrière le même domaine (/api) : cookie de session HttpOnly + CSRF, sans CORS.
const API_URL = process.env.PME360_API_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
