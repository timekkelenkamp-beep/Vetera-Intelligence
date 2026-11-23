/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"SF Pro Display"', '"Segoe UI Variable Text"',
               '"Segoe UI"', 'system-ui', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['"SF Mono"', 'ui-monospace', '"Cascadia Code"', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        ink: { DEFAULT: "#1d1d1f", soft: "#424245", muted: "#6e6e73", faint: "#86868b" },
        surface: { DEFAULT: "#f5f5f7", raised: "#ffffff", sunken: "#ebebed" },
        line: { DEFAULT: "rgba(0,0,0,0.08)", strong: "rgba(0,0,0,0.14)" },
        accent: { DEFAULT: "var(--accent)", soft: "var(--accent-soft)", ink: "var(--accent-ink)" },
        positive: { DEFAULT: "#1f7a3a", soft: "#e8f4ec" },
        negative: { DEFAULT: "#b3261e", soft: "#fbeceb" },
        caution: { DEFAULT: "#9a5b00", soft: "#fdf3e3" },
        info: { DEFAULT: "#0a5bb5", soft: "#e9f1fb" },
      },
      borderRadius: { xl: "14px", "2xl": "18px", "3xl": "24px" },
      boxShadow: {
        soft: "0 1px 2px rgba(0,0,0,0.04), 0 2px 8px rgba(0,0,0,0.04)",
        lift: "0 2px 6px rgba(0,0,0,0.05), 0 12px 32px rgba(0,0,0,0.07)",
        ring: "0 0 0 4px var(--accent-soft)",
      },
      letterSpacing: { tightest: "-0.035em" },
    },
  },
  plugins: [],
};
