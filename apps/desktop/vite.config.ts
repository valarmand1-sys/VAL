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
});
