import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite config for the React frontend. Dev server runs on port 5173 by
// default, which is also what backend/.env.example's CORS_ALLOWED_ORIGINS
// expects during local development.
export default defineConfig({
  plugins: [react()],
});
