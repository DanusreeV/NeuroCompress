import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// The single .env lives in the project root (one level above /frontend).
export default defineConfig(({ mode }) => {
  const envDir = path.resolve(__dirname, "..");
  const env = loadEnv(mode, envDir, "");
  // Where the FastAPI backend listens. The start scripts export VITE_API_PROXY_TARGET with the real
  // (possibly auto-selected) backend port, so changing ports never breaks the connection.
  const target =
    process.env.VITE_API_PROXY_TARGET ||
    env.VITE_API_PROXY_TARGET ||
    `http://127.0.0.1:${env.BACKEND_PORT || 8000}`;
  const port = Number(process.env.VITE_PORT || env.VITE_PORT || 5173);
  const proxy = { "/api": { target, changeOrigin: true } };
  return {
    plugins: [react()],
    envDir,
    server: { port, strictPort: false, proxy },
    preview: { port, proxy },
  };
});
