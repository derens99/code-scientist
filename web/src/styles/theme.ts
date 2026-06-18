import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "blue",
  defaultRadius: "sm",
  fontFamily:
    "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
  headings: {
    fontFamily:
      "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    sizes: {
      h1: { fontSize: rem(26), lineHeight: "1.2" },
      h2: { fontSize: rem(20), lineHeight: "1.25" },
      h3: { fontSize: rem(16), lineHeight: "1.3" }
    }
  },
  colors: {
    ink: [
      "#f7f8fb",
      "#ebeef5",
      "#d8deea",
      "#b8c1d1",
      "#8d98ad",
      "#667189",
      "#4f596e",
      "#394151",
      "#272e3b",
      "#161c27"
    ]
  }
});
