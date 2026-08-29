import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // The agent (agent/server.py) serves the real API. Proxying /api here
      // means the browser talks to one origin and never needs CORS.
      proxy: {
        "/api": {
          target: env.VITE_AGENT_URL || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
