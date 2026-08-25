import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The deterministic core serves at :8000. In dev we proxy /api -> that origin
// (stripping the prefix) so the app is origin-agnostic; in prod set VITE_API_BASE.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Split the heavy charting lib and the React runtime into their own
        // long-lived chunks so app code can change without re-downloading them.
        manualChunks: {
          recharts: ["recharts"],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
