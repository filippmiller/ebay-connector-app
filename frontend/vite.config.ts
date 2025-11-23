import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Allow overriding backend/port via env without changing code:
// - VITE_BACKEND_URL (e.g. http://127.0.0.1:8081)
// - VITE_BACKEND_PORT (fallback if URL not provided)
// - VITE_DEV_PORT (frontend dev server port)
const backendTarget = process.env.VITE_BACKEND_URL || `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || "8000"}`
const devPort = Number(process.env.VITE_DEV_PORT || 5173)

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: devPort,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
        // DO NOT strip /api prefix - backend routes are mounted at /api/*
      },
    },
  },
})

