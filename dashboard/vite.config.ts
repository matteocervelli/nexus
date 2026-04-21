import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  plugins: [TanStackRouterVite(), react()],
  resolve: {
    alias: {
      "@adlimen/ui": "@adlimen/ui-react",
      "@": new URL("./src", import.meta.url).pathname,
    },
  },
  server: {
    port: 5273,
    proxy: {
      "/nexus/api": process.env["VITE_API_URL"] ?? "http://localhost:8101",
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: "modern-compiler",
      },
    },
  },
});
