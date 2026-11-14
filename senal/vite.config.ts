import { createReadStream, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Connect } from "vite";

const SENAL_JSON = fileURLToPath(new URL("../output/senal/senal.json", import.meta.url));

// Serves the engine's output at /senal.json in both `vite` and `vite preview`; 404 if absent.
const serveSenalJson: Connect.NextHandleFunction = (req, res, next) => {
  if (req.url?.split("?")[0] !== "/senal.json") return next();
  if (!existsSync(SENAL_JSON)) {
    res.statusCode = 404;
    return res.end("senal.json not found");
  }
  res.setHeader("Content-Type", "application/json");
  createReadStream(SENAL_JSON).pipe(res);
};

export default defineConfig({
  base: "./",
  plugins: [
    {
      name: "senal-json",
      configureServer: (s) => void s.middlewares.use(serveSenalJson),
      configurePreviewServer: (s) => void s.middlewares.use(serveSenalJson),
    },
  ],
});
