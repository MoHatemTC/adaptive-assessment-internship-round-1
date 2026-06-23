import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "var(--color-primary)",
        "primary-60": "var(--color-primary-60)",
        "primary-20": "var(--color-primary-20)",
        "primary-hover": "var(--color-primary-hover)",
        "primary-container": "var(--color-primary-container)",
        "on-primary": "var(--color-on-primary)",
        "on-primary-container": "var(--color-on-primary-container)",
        secondary: "var(--color-secondary)",
        tertiary: "var(--color-tertiary)",
        neutral: "var(--color-neutral)",
        "on-surface": "var(--color-on-surface)",
        "on-surface-variant": "var(--color-on-surface-variant)",
        surface: "var(--color-surface)",
        "surface-muted": "var(--color-surface-muted)",
        "surface-container-low": "var(--color-surface-container-low)",
        "surface-container-high": "var(--color-surface-container-high)",
        "surface-container-highest": "var(--color-surface-container-highest)",
        background: "var(--color-background)",
        border: "var(--color-border)",
        "border-base": "var(--color-border-base)",
        outline: "var(--color-outline)",
        success: "var(--color-success)",
        error: "var(--color-error)",
        "editor-bg": "var(--color-editor-bg)",
        "editor-header": "var(--color-editor-header)",
        "editor-border": "var(--color-editor-border)",
        "editor-chip": "var(--color-editor-chip)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        full: "var(--radius-full)",
      },
      spacing: {
        xs: "var(--spacing-xs)",
        sm: "var(--spacing-sm)",
        md: "var(--spacing-md)",
        lg: "var(--spacing-lg)",
        gutter: "var(--spacing-gutter)",
      },
      fontFamily: {
        jakarta: ["var(--font-jakarta)"],
      },
      fontSize: {
        "headline-sm": ["25px", { lineHeight: "30px", fontWeight: "700" }],
        "title-md": ["21px", { lineHeight: "25px", fontWeight: "600" }],
        "body-md": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "body-sm": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "label-md": ["14px", { lineHeight: "18px", fontWeight: "600" }],
        "label-sm": ["12px", { lineHeight: "16px", fontWeight: "600" }],
      },
      boxShadow: {
        card: "0px 4px 20px rgba(0, 0, 0, 0.04)",
        editor: "0px 8px 32px rgba(0, 0, 0, 0.12)",
      },
    },
  },
  plugins: [],
};

export default config;
