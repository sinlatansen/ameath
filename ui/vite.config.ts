import { defineConfig } from "vite";

// https://v2.tauri.app/start/frontend/vite/
export default defineConfig(async () => ({
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/crates/**"],
    },
  },
}));
