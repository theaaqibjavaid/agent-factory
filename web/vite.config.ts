import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Studio talks to the AgentFactory platform API on the same origin in
// production (FastAPI serves the built assets). In dev, proxy /api to the
// local platform backend so there are no CORS concerns.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
