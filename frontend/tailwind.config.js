/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      colors: {
        paper: "#faf9f7",
        brand: { 50: "#eef4f3", 100: "#dbe9e7", 500: "#3b6f6c", 600: "#2b5755", 700: "#1f4240" },
      },
    },
  },
  plugins: [],
};
