import type { Config } from "tailwindcss";

// Tokens deliberately mirror the host app's dark navy/cyan system so LeadRank
// reads as a native SaaSquatch module rather than a bolted-on prototype.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: { 0: "#0E1420", 1: "#161E2E", 2: "#1E2838", 3: "#27334A" },
        line: "#2A3547",
        hi: "#E8EDF5",
        lo: "#8A98AE",
        primary: { DEFAULT: "#35B6E8", soft: "#1B5C77" },
        band: { a: "#3FBF8F", b: "#5BA8D6", c: "#C9A227", d: "#C0576B" },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      fontVariantNumeric: { tabular: "tabular-nums" },
    },
  },
  plugins: [],
};
export default config;
