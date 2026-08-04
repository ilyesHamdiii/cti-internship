import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#090d13",
        panel: "#101720",
        border: "#223044",
        accent: "#28d3a6",
        danger: "#ff5a6a",
        warning: "#f6c453"
      }
    }
  },
  plugins: []
};

export default config;
