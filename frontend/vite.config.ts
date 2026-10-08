import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// MeritOS fixed dev ports (must not collide with ENMA/QResolve):
//   frontend dev: 127.0.0.1:5421  (override with FRONTEND_PORT)
//   backend:      127.0.0.1:8421  (override with BACKEND_PORT)
const frontendPort = Number(process.env.FRONTEND_PORT) || 5421;
const backendPort = Number(process.env.BACKEND_PORT) || 8421;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": { target: `http://127.0.0.1:${backendPort}` },
    },
  },
  build: {
    outDir: "dist",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
    restoreMocks: true,
    unstubGlobals: true,
  },
});
