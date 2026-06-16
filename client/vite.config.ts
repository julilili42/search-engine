import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Forward API calls to the FastAPI backend so we avoid CORS in dev.
    proxy: {
      "/search": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
})
