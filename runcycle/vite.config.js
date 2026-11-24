import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

// Serve the exported model folder (Firefighter.pmx + tex/) as static files.
// The victim and cat models live in ../models and are imported by URL from main.js,
// so the dev server must be allowed to read the repo root.
export default defineConfig({
  publicDir: '../pmx',
  server: {
    fs: { allow: [fileURLToPath(new URL('..', import.meta.url))] },
  },
});
