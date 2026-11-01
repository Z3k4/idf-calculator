import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// En dev, les appels API sont relayés vers FastAPI (uvicorn sur le port 8000)
const API = process.env.API_URL ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/stations': API,
      '/health': API,
      '/journeys': API,
      '/places': API,
      '/itineraries': API,
    },
  },
});
