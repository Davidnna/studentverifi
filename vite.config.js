import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  root: 'frontend',
  base: '/',
  build: { outDir: '../public', emptyOutDir: false, sourcemap: false, manifest: false, target: 'es2020' },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:5000', '/health': 'http://127.0.0.1:5000' }
  }
});
