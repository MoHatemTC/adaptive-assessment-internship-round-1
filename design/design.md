---
version: alpha
name: Sprints AI
description: A bright, optimistic learning platform with soft skies, vivid blue accents, and friendly editorial typography.
colors:
  primary: "#004EFF"
  primary-60: "#3374FF"
  primary-20: "#CCE0FF"
  secondary: "#24D6D6"
  tertiary: "#FFB300"
  neutral: "#343434"
  surface: "#FBFBFD"
  surface-muted: "#E6EEFF"
  on-surface: "#1F2430"
  border: "#D8DDF0"
  border-strong: "#004EFF40"
  success: "#14B86A"
  error: "#E5484D"
typography:
  headline-display:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 48px
    fontWeight: 700
    lineHeight: 56px
    letterSpacing: 0px
  headline-lg:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 36px
    fontWeight: 700
    lineHeight: 43px
    letterSpacing: 0px
  headline-md:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 30px
    fontWeight: 700
    lineHeight: 40px
    letterSpacing: 0px
  headline-sm:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 25px
    fontWeight: 700
    lineHeight: 30px
    letterSpacing: 0px
  title-md:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 21px
    fontWeight: 600
    lineHeight: 25px
    letterSpacing: 0px
  body-lg:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 27px
    letterSpacing: 0px
  body-md:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 24px
    letterSpacing: 0px
  body-sm:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
    letterSpacing: 0px
  label-lg:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 16px
    fontWeight: 600
    lineHeight: 20px
    letterSpacing: 0px
  label-md:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 18px
    letterSpacing: 0px
  label-sm:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 12px
    fontWeight: 600
    lineHeight: 16px
    letterSpacing: 0.04em
  overline:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: 12px
    fontWeight: 600
    lineHeight: 16px
    letterSpacing: 0.08em
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 12px
  xl: 24px
  full: 9999px
spacing:
  xs: 8px
  sm: 20px
  md: 32px
  lg: 48px
  xl: 76px
  gutter: 24px
  section: 96px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
    height: "43px"
  button-primary-hover:
    backgroundColor: "{colors.primary-60}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.neutral}"
    typography: "{typography.label-md}"
    rounded: "{rounded.sm}"
    padding: "12px 24px"
    height: "43px"
  button-tertiary:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.none}"
    padding: "0px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.neutral}"
    rounded: "{rounded.xl}"
    padding: "24px"
  card-muted:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.neutral}"
    rounded: "{rounded.xl}"
    padding: "24px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.full}"
    padding: "12px 16px"
    height: "44px"
  chip:
    backgroundColor: "{colors.primary-20}"
    textColor: "{colors.primary}"
    rounded: "{rounded.full}"
    padding: "10px 20px"
  stat-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.neutral}"
    rounded: "{rounded.xl}"
    padding: "24px"
  badge-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.full}"
    padding: "8px 16px"
---

# Sprints AI

## Overview
Sprints AI feels upbeat, modern, and reassuringly product-led. The interface is designed for students and career switchers, so the tone stays approachable while still signaling progress, speed, and outcomes. Visual density is moderate: roomy hero spacing and soft cards create calm, while bright blue accents keep the experience energetic and goal-oriented.

## Colors
- **Primary (#004EFF):** The signature electric blue used for calls to action, nav emphasis, icons, progress indicators, and key highlights. It gives the system its "fast and confident" personality.
- **Primary-60 (#3374FF):** A lighter blue for hover states, secondary emphasis, and subtle depth without losing brand consistency.
- **Primary-20 (#CCE0FF):** A pale blue wash for chips, tags, and gentle background accents.
- **Secondary (#24D6D6):** A fresh aqua used for supportive accent moments, illustrated motifs, and alternate stat treatments.
- **Tertiary (#FFB300):** A warm gold used sparingly to break up the cool palette and highlight performance metrics or special outcomes.
- **Neutral (#343434):** The main text color; a soft charcoal that reads clearly without the harshness of pure black.
- **Surface (#FBFBFD):** The near-white page background, keeping the UI light, spacious, and airy.
- **Surface-muted (#E6EEFF):** A pale sky-blue surface for featured cards and informational blocks.
- **On-surface (#1F2430):** A deeper near-navy for higher-contrast text on light surfaces when needed.
- **Border (#D8DDF0):** A quiet cool border tone that helps define inputs and containers without adding visual noise.
- **Border-strong (#004EFF40):** A translucent blue border used for cards and emphasis surfaces.
- **Success (#14B86A):** Reserved for positive status, completion, or success feedback.
- **Error (#E5484D):** Reserved for validation and destructive states.

## Typography

The system uses **Plus Jakarta Sans** — a free, open-source geometric sans-serif available on Google Fonts. It is the closest open-source match to Gilroy's personality: rounded, confident, and highly legible at all sizes. It ships in all required weights (Regular 400, Medium 500, SemiBold 600, Bold 700) and is production-safe with zero licensing cost.

Load it in your Next.js project via `next/font/google`:

```tsx
import { Plus_Jakarta_Sans } from "next/font/google";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-jakarta",
});
```

Then set `font-family: var(--font-jakarta), sans-serif` as your base.

Headlines are bold and compact, which keeps the hero message punchy and easy to scan; the largest display styles should carry the most emotional weight. Body text is clean and readable with moderate line height, while labels and buttons lean on semi-bold or medium weights to feel crisp and interactive.

Uppercase is used sparingly, mostly for compact labels and stat captions rather than long navigation items. Letter spacing remains mostly neutral, with only small tracking for tiny labels and overlines to improve legibility at smaller sizes.

## Layout & Spacing
The layout is built around a wide, center-aligned desktop canvas with generous horizontal breathing room. Sections are stacked vertically with large gaps between the hero, stats row, and content introduction, creating a calm, guided scroll. Spacing follows a loose 8px-based rhythm, but key section separations are larger and more expressive, using 32px, 48px, and 76px steps for clear hierarchy.

Cards and feature blocks use substantial internal padding, typically 24px, while buttons and controls keep compact vertical sizing to feel efficient. Containers are wide and fluid rather than tightly boxed, letting illustration and whitespace contribute to the brand's open, optimistic mood.

## Elevation & Depth
Depth is subtle and friendly rather than dramatic. The interface relies on soft shadows, pale tonal layers, and border contrast instead of heavy z-axis stacking. Primary buttons receive the strongest shadow treatment to make the CTA feel pressable and important, while cards use light shadowing and cool borders to separate them from the soft background.

Flat elements are acceptable when they are meant to feel secondary, such as links or inline nav items. Use color and tonal background shifts first, then shadow only where interaction or importance needs reinforcement.

## Shapes
The shape language is rounded, approachable, and slightly playful. Buttons and inputs use soft radii, with pills and chips leaning fully rounded and cards using a generous 24px corner radius. The overall effect is polished and friendly rather than sharp or corporate.

Avoid overly angular geometry; even structural elements should feel softened to match the learning-oriented brand.

## Components
Buttons are the clearest expression of the brand:
- `button-primary` is the main CTA style: filled primary blue, white text, 12px by 24px padding, 43px height, and rounded medium corners. It should be used for high-intent actions like "Get Started" and "Get Job-Ready."
- `button-primary-hover` should lift slightly in tone using `primary-60`.
- `button-secondary` is a transparent or outlined alternative with dark text, suitable for lower-priority actions in navigation or supporting controls.
- `button-tertiary` is text-only and should be reserved for subtle links or inline actions.

Cards should feel airy and informative:
- `card` and `card-muted` use 24px padding, generous rounding, and either white or pale blue surfaces.
- Stat cards should stay compact but still feel premium, with small icon treatments, a thin top accent, and soft shadowing.

Inputs are rounded pill fields with a light border and clear placeholder text. They should remain understated, with the search bar acting as a calm utility rather than a dominant element.

Chips and badges are important for wayfinding and status:
- `chip` uses a pale blue fill with primary text for lightweight tagging, like "Keep Learning."
- `badge-outline` is ideal for compact counters or status pills and should remain simple and legible.

Navigation should be minimal, icon-assisted, and text-forward. Icons are thin-lined and circular, often paired with concise labels. Use clear hierarchy and avoid overdecorating lists or forms; the brand works best when content, progress cues, and calls to action stay the focus.

## Do's and Don'ts
- Do keep the interface bright, open, and optimistic with plenty of whitespace.
- Do use the primary blue consistently for critical actions and progress indicators.
- Do favor rounded, pill-like controls for inputs, chips, and CTAs.
- Do keep typography bold and compact for headlines, with readable line spacing for body copy.
- Don't introduce heavy black shadows, dark panels, or severe contrast.
- Don't use sharp corners or dense, boxed layouts that fight the airy learning experience.
- Don't overuse accent colors; let blue remain dominant and use aqua or gold only as supportive emphasis.
- Don't make secondary actions compete visually with the main job-ready CTA.
