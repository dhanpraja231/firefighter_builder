import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The rigged character models live in ../models (shared with the character tooling), so the dev
  // server must be allowed to read the repo root. `vite build` copies them into dist/assets.
  server: {
    port: Number(process.env.PORT) || 5173,
    host: true,
    fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] },
  },
  assetsInclude: ["**/*.glb"],
});
