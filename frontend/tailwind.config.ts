import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: {
        "2xl": "1280px",
      },
    },
    extend: {
      colors: {
        background: "#050505",
        foreground: "#FAFAFA",
        accent: {
          DEFAULT: "#00FF85",
          foreground: "#050505",
        },
        muted: {
          DEFAULT: "rgba(255,255,255,0.04)",
          foreground: "rgba(255,255,255,0.6)",
        },
        border: "rgba(255,255,255,0.10)",
      },
      fontFamily: {
        display: ["var(--font-bebas)", "sans-serif"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      maxWidth: {
        container: "1280px",
      },
      keyframes: {
        "ticker-x": {
          "0%": { transform: "translateX(0%)" },
          "100%": { transform: "translateX(-50%)" },
        },
        "pulse-dot": {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
        "glow-pulse": {
          "0%,100%": { opacity: "0.5" },
          "50%": { opacity: "0.85" },
        },
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        ticker: "ticker-x 40s linear infinite",
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
        "glow-pulse": "glow-pulse 6s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
