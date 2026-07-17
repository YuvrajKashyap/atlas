import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "api/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["api/**/*.ts", "src/state/**/*.ts", "src/state/**/*.tsx"],
    },
  },
});
