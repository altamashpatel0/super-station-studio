import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// V0.2: the React dev server proxies /api to the FastAPI backend so the
// UI can call relative paths ("/api/library/songs") in both dev and
// the eventual Electron-packaged build.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
