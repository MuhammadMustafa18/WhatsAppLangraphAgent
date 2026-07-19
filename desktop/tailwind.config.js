/** @type {import('tailwindcss').Config} */
// Cohere design system tokens. See `cohere-design-analysis.md`.
// Proprietary CohereText / Unica77 / CohereMono are replaced with documented
// fallbacks: Space Grotesk (display), Inter (UI/body), JetBrains Mono (mono).
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand & accents
        primary: "#17171c",
        "cohere-black": "#000000",
        ink: "#212121",
        "deep-green": "#003c33",
        "dark-navy": "#071829",
        "action-blue": "#1863dc",
        "focus-blue": "#4c6ee6",
        coral: "#ff7759",
        "coral-soft": "#ffad9b",
        "form-focus": "#9b60aa",
        error: "#b30000",
        // Surfaces
        canvas: "#ffffff",
        "soft-stone": "#eeece7",
        "pale-green": "#edfce9",
        "pale-blue": "#f1f5ff",
        // Rules
        hairline: "#d9d9dd",
        "border-light": "#e5e7eb",
        "card-border": "#f2f2f2",
        // Text
        muted: "#93939f",
        slate: "#75758a",
        "body-muted": "#616161",
        "on-primary": "#ffffff",
        "on-dark": "#ffffff",
      },
      fontFamily: {
        // Display headlines — replaces CohereText
        display: ['"Space Grotesk"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        // UI / body — replaces Unica77
        sans: ["Inter", "ui-sans-serif", "system-ui", "Arial", "sans-serif"],
        // Mono labels — replaces CohereMono
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // Hero display scale
        "hero-display": ["96px", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "product-display": ["72px", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "section-display": ["60px", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "section-heading": ["48px", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        "card-heading": ["32px", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        "feature-heading": ["24px", { lineHeight: "1.3", letterSpacing: "0" }],
        "body-large": ["18px", { lineHeight: "1.4", letterSpacing: "0" }],
        "body": ["16px", { lineHeight: "1.5", letterSpacing: "0" }],
        "button": ["14px", { lineHeight: "1.71", letterSpacing: "0" }],
        "caption": ["14px", { lineHeight: "1.4", letterSpacing: "0" }],
        "mono-label": [
          "14px",
          { lineHeight: "1.4", letterSpacing: "0.02em" },
        ],
        "micro": ["12px", { lineHeight: "1.4", letterSpacing: "0" }],
      },
      borderRadius: {
        xs: "4px",
        sm: "8px",
        md: "16px",
        lg: "22px",
        xl: "30px",
        pill: "32px",
      },
      spacing: {
        xxs: "2px",
        xs: "6px",
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
        xxl: "32px",
        section: "80px",
      },
      ringColor: {
        focus: "#4c6ee6",
      },
      boxShadow: {
        // Cohere is mostly flat — keep these very subtle.
        "media-lift":
          "0 1px 0 rgba(0,0,0,0.04), 0 0 0 1px rgba(217,217,221,0.6) inset",
      },
    },
  },
  plugins: [],
};
