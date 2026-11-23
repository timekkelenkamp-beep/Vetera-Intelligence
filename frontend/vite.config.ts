import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Ontwikkelmodus: frontend op 5173, API-verzoeken naar de lokale backend op 3000.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:3000", changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
});
