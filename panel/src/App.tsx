import { useEffect } from "react";
import { Route, Routes, useLocation } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { useMeta } from "./api/hooks";
import { Toasts } from "./components/Overlays";
import { Sidebar } from "./components/Sidebar";
import { useTheme } from "./design/theme";
import { Inicio } from "./pages/Inicio";
import { Soon } from "./pages/Soon";
import { Revisar } from "./pages/Revisar";

const SOON: [string, string, string][] = [
  ["/crear", "Crear", "Elegir formato y tema, y ver el vídeo hacerse en vivo."],
  ["/cola", "Cola", "Cuántos días quedan de cada formato y lo próximo en salir."],
  ["/subir", "Subir", "El estado de cada plataforma."],
  ["/rendimiento", "Rendimiento", "Todas las gráficas del canal."],
  ["/comentarios", "Comentarios", "Responder con una sugerencia lista."],
  ["/biblioteca", "Biblioteca", "Todos los vídeos con sus miniaturas y vistas."],
];

export function App() {
  const meta = useMeta();
  const { theme, mode, setMode, until } = useTheme();
  const loc = useLocation();
  useEffect(() => {
    const vis = () => document.documentElement.classList.toggle("paused", document.visibilityState !== "visible");
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, []);
  return (
    <div className="shell">
      <div className="blobs" aria-hidden="true"><i /><i /><i /></div>
      <Sidebar meta={meta.data} />
      <main className="main" id="main">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={loc.pathname} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.16, ease: [0.2, 0.8, 0.2, 1] }}>
            <Routes location={loc}>
              <Route path="/" element={<Inicio meta={meta.data} theme={theme} mode={mode} until={until} setMode={setMode} />} />
              <Route path="/revisar" element={<Revisar />} />
              {SOON.map(([p, t, w]) => <Route key={p} path={p} element={<Soon title={t} what={w} meta={meta.data} />} />)}
              <Route path="*" element={<Soon title="Esta página" what="No existe todavía." meta={meta.data} />} />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
      <Toasts />
    </div>
  );
}
