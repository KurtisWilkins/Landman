import type { Config } from "tailwindcss";

/**
 * RJourney brand theme — the single source of truth for color, type, and shape tokens.
 * Values extracted from the live site (rjourney.com, Breakdance `global-settings.css`):
 * brand navy #25314B, ink #252525, warm paper #FCFBFA, white surfaces, gold accent #FEBB20,
 * Gabarito as the brand typeface. Semantic names map to app roles (brand action, body ink,
 * page/surface, accent); change a value here and the whole app re-themes.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#25314B", hover: "#1b2438" }, // primary actions, headings, links
        ink: { DEFAULT: "#252525", muted: "#6b7280" }, // body text / muted text
        paper: "#FCFBFA", // page background (warm off-white)
        surface: "#FFFFFF", // cards, inputs
        line: "#E5E7EB", // borders
        accent: { DEFAULT: "#FEBB20", ink: "#7A5512" }, // gold; `ink` is the AA-safe text-on-light gold
        success: { DEFAULT: "#047857" },
        danger: { DEFAULT: "#B91C1C", soft: "#EF4444" },
      },
      fontFamily: {
        // Brand face for all UI text; figures stay monospaced for tabular alignment.
        sans: [
          "Gabarito",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        figure: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // Brand modular type scale (×1.25, anchored at 16px) — applied to bare headings in base.
      fontSize: {
        h1: ["2.027rem", { lineHeight: "1.2", fontWeight: "700" }],
        h2: ["1.625rem", { lineHeight: "1.2", fontWeight: "700" }],
        h3: ["1.3rem", { lineHeight: "1.25", fontWeight: "600" }],
        h4: ["1.2rem", { lineHeight: "1.3", fontWeight: "600" }],
        eyebrow: ["0.75rem", { lineHeight: "1", letterSpacing: "0.12em" }],
      },
      borderRadius: {
        DEFAULT: "0.1875rem", // 3px — brand button/input radius
      },
    },
  },
  plugins: [],
} satisfies Config;
