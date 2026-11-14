import { useEffect, useRef, useState } from "react";
import { Moon, Sun } from "lucide-react";
import type { ThemeMode } from "../design/theme";
import type { ThemeName } from "../api/contract";

/** «☾ Noche hasta las 7:00 (NY)» and a small menu: automatic, always day, always night. */
export function ThemeChip({ theme, mode, until, setMode }: { theme: ThemeName; mode: ThemeMode; until: string; setMode: (m: ThemeMode) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("mousedown", close);
    addEventListener("keydown", esc);
    return () => {
      removeEventListener("mousedown", close);
      removeEventListener("keydown", esc);
    };
  }, [open]);
  const Icon = theme === "night" ? Moon : Sun;
  const label = mode === "auto" ? `${theme === "night" ? "Noche" : "Día"} hasta las ${until} (NY)` : theme === "night" ? "Siempre noche" : "Siempre día";
  const opts: [ThemeMode, string][] = [["auto", "Automático (Nueva York)"], ["day", "Siempre día"], ["night", "Siempre noche"]];
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" className="chip" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon size={14} aria-hidden="true" /> {label}
      </button>
      {open && (
        <div className="menu" role="menu">
          {opts.map(([m, l]) => (
            <button key={m} type="button" role="menuitemradio" aria-checked={mode === m} onClick={() => { setMode(m); setOpen(false); }}>{l}</button>
          ))}
        </div>
      )}
    </div>
  );
}
