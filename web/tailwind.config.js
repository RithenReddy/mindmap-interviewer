/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        deep: "#090c14",
        panel: "#0f1728",
        glow: "#56e6ff",
        accent: "#8c74ff",
      },
      boxShadow: {
        neon: "0 0 40px rgba(86, 230, 255, 0.2)",
      },
    },
  },
  plugins: [],
};
