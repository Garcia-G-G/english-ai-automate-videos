import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The panel is served by the local API on 127.0.0.1:8501 (./run_panel.sh, the URL Garcia always used).
// In dev, Vite proxies /api there, so the app and the API share one origin.
const api = { "/api": "http://127.0.0.1:8501", "/media": "http://127.0.0.1:8501" };

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy: api },
  preview: { proxy: process.env.PANEL_NO_PROXY ? {} : api },
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 300 },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
