import { dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: { NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000" },
  // The repo root has its own package-lock.json (commit-tooling only, see
  // ../package.json) — pin Turbopack's root here so it doesn't try to infer
  // it from that sibling lockfile and lose track of this app's own pages.
  turbopack: { root: __dirname },
};
export default nextConfig;
