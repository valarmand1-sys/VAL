/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The desktop shell is served to Tauri from ../dist. It reaches the FastAPI
// service over HTTP and imports no other workspace component
// (01-architecture.md §3).
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    // Vitest stubs every stylesheet to an empty string unless told otherwise;
    // the review-scroll tests need the real cascade applied to rendered nodes.
    css: { include: [/styles\.css$/] },
    // Every test starts with a `fetch` that refuses: none may reach a real service.
    setupFiles: ["src/testSetup.ts"],
  },
});
