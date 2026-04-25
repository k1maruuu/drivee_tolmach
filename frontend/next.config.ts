import type { NextConfig } from "next";
import path from "node:path";

/** Server-side rewrite target (Docker Compose service name vs host dev). */
const internalApiDest = (
  process.env.NEXT_INTERNAL_API_DEST ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  /** Lock workspace root to this app (avoids picking a parent `pnpm-lock.yaml`). */
  turbopack: { root: path.resolve(process.cwd()) },
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiDest}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
