import { defineConfig } from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths()],
  // Não carregar o postcss.config.mjs (plugin do Tailwind v4 como string)
  // durante os testes — eles não tocam em CSS.
  css: { postcss: { plugins: [] } },
  test: {
    environment: "node",
    include: ["__tests__/**/*.test.ts", "lib/**/*.test.ts"],
  },
});
