import type { Config } from "tailwindcss";

// Design tokens named per the design doc §6 (forest ink, bone paper, brass accent, mono
// for figures). Exact hex values are taken from rjourney-acquisitions-wireframes.html —
// TODO(stream-D): replace these placeholders with the wireframe's measured values.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        forest: { ink: "#1c2b25", DEFAULT: "#24463a" },
        bone: { paper: "#f5f1e6", DEFAULT: "#efe9d8" },
        brass: { accent: "#b08a3e" },
      },
      fontFamily: {
        figure: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
