import type { NextConfig } from "next";

const config: NextConfig = {
  // The Portal renders server-side against the EAIRN API; nothing is bundled
  // from the assessment itself, so a snapshot never leaks into a static asset.
  env: { EAIRN_API_URL: process.env.EAIRN_API_URL ?? "http://127.0.0.1:8000" },
};

export default config;
