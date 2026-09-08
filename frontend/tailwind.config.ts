import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // "Reading room" palette — deep ink for dark mode, warm parchment
        // for light mode, a single amber "index-tab" accent throughout.
        // Deliberately not terracotta/cream (overused) or neon-on-black.
        ink: {
          50: "#f4f5f7",
          100: "#e5e7ec",
          200: "#c7cbd6",
          300: "#9ba1b3",
          400: "#6b7288",
          500: "#4a4f63",
          600: "#363a4a",
          700: "#272a37",
          800: "#1a1c26",
          900: "#12131a",
          950: "#0a0a0f",
        },
        parchment: {
          50: "#fdfcf9",
          100: "#f8f5ee",
          200: "#efe9db",
          300: "#e2d8c0",
        },
        index: {
          // the amber "card catalog tab" accent
          400: "#e0a94e",
          500: "#c98f34",
          600: "#a8721f",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(10, 10, 15, 0.06), 0 4px 16px rgba(10, 10, 15, 0.06)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards",
      },
    },
  },
  plugins: [],
};

export default config;
