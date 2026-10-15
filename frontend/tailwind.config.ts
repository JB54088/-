import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#182230",
        muted: "#667085",
        brand: { 50: "#eff8ff", 100: "#dff0ff", 500: "#3488e8", 600: "#1d6fd1", 700: "#1556a8" },
        mint: "#13b887",
      },
      boxShadow: { soft: "0 4px 18px rgba(22, 34, 51, .045)" },
    },
  },
  plugins: [],
};

export default config;
