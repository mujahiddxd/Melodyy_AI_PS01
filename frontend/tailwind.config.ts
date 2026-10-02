import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: "#F5F1E8",
        ink: "#17151F",
        lavender: "#C3B1F5",
        "lavender-deep": "#6E56D9",
        butter: "#F9D56E",
        mint: "#B9E4A1",
        sky: "#A8CCF4",
        coral: "#F2A58B",
        "cream-yellow": "#FDF1D0",
        danger: "#D64545",
        "danger-fill": "#FDECEC",
        muted: "#5A5870",
      },
      borderRadius: { card: "28px", input: "20px" },
      boxShadow: {
        brutal: "6px 6px 0 0 #17151F",
        "brutal-sm": "0 4px 0 0 #17151F",
        "brutal-purple": "0 4px 0 0 #6E56D9",
        clay: "0 6px 14px rgba(23,21,31,0.10), inset 0 2px 0 rgba(255,255,255,0.8)",
      },
      fontFamily: {
        display: ["var(--font-display)", "Bricolage Grotesque", "sans-serif"],
        sans: ["var(--font-sans)", "Outfit", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
