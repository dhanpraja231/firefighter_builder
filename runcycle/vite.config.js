import { defineConfig } from 'vite';

// Serve the exported model folder (Firefighter.pmx + tex/) as static files.
export default defineConfig({
  publicDir: '../pmx',
});
