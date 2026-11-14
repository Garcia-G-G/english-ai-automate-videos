import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource/fredoka/latin-500.css";
import "@fontsource/fredoka/latin-600.css";
import "@fontsource/fredoka/latin-700.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/manrope/latin-800.css";
import "@fontsource/silkscreen/latin-400.css";
import "./design/app.css";
import { App } from "./App";
import { EventsProvider } from "./lib/events";
import { themeAt } from "./design/theme";

// Paint the right theme before React mounts, so there is no flash.
try {
  const m = localStorage.getItem("eu.themeMode");
  document.documentElement.dataset.theme = m === "day" || m === "night" ? m : themeAt(new Date());
} catch {
  document.documentElement.dataset.theme = themeAt(new Date());
}

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 20_000, refetchOnWindowFocus: true, retry: 1, placeholderData: (prev: unknown) => prev } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <EventsProvider>
          <App />
        </EventsProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
