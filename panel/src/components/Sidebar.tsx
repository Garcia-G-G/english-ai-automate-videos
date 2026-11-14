import { useEffect, useRef } from "react";
import { NavLink } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, Clapperboard, Eye, House, LayoutGrid, ListOrdered, MessageCircle, Upload, type LucideIcon } from "lucide-react";
import type { Meta } from "../api/contract";
import { apiGet } from "../api/client";
import { keys } from "../api/hooks";
import { usd } from "../lib/format";
import { BubiCorner } from "./Overlays";

interface Item { to: string; label: string; icon: LucideIcon; badge?: (m: Meta) => number; soft?: boolean; prefetch?: () => void }

function Badge({ v, soft }: { v: number; soft?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(v);
  useEffect(() => {
    if (prev.current !== v && ref.current) {
      ref.current.classList.remove("bump");
      void ref.current.offsetWidth;
      ref.current.classList.add("bump");
    }
    prev.current = v;
  }, [v]);
  if (v <= 0) return null;
  return <span ref={ref} className={`bd${soft ? " soft" : ""}`}>{v}</span>;
}

export function Sidebar({ meta }: { meta: Meta | undefined }) {
  const qc = useQueryClient();
  const prefetchHome = () => void qc.prefetchQuery({ queryKey: keys.home, queryFn: () => apiGet("/api/home"), staleTime: 30_000 });
  const groups: [string, Item[]][] = [
    ["Producir", [
      { to: "/", label: "Inicio", icon: House, prefetch: prefetchHome },
      { to: "/crear", label: "Crear", icon: Clapperboard },
      { to: "/cola", label: "Cola", icon: ListOrdered, badge: (m) => m.counts.queue, soft: true },
      { to: "/revisar", label: "Revisar", icon: Eye, badge: (m) => m.counts.review },
      { to: "/subir", label: "Subir", icon: Upload, badge: (m) => m.counts.upload },
    ]],
    ["Canal", [
      { to: "/rendimiento", label: "Rendimiento", icon: BarChart3 },
      { to: "/comentarios", label: "Comentarios", icon: MessageCircle, badge: (m) => m.counts.comments },
      { to: "/biblioteca", label: "Biblioteca", icon: LayoutGrid },
    ]],
  ];
  const or = meta?.openrouter;
  return (
    <nav className="nav" aria-label="Secciones">
      <NavLink to="/" className="brand" onMouseEnter={prefetchHome}>
        <img src="/bubi/simbolo.webp" alt="" width={40} height={40} />
        <div><b>English Unlimited</b><small>Estudio de vídeos</small></div>
      </NavLink>
      {groups.map(([g, items]) => (
        <div key={g} style={{ display: "contents" }}>
          <div className="navlabel">{g}</div>
          {items.map((it) => (
            <NavLink key={it.to} to={it.to} end={it.to === "/"} className={({ isActive }) => `ni${isActive ? " active" : ""}`}
              onMouseEnter={it.prefetch} onFocus={it.prefetch} title={it.label}>
              <it.icon aria-hidden="true" />
              <span className="lbl">{it.label}</span>
              {meta && it.badge && <Badge v={it.badge(meta)} soft={it.soft} />}
            </NavLink>
          ))}
        </div>
      ))}
      <div className="sp" />
      <BubiCorner />
      {or && (
        <div className="meter" aria-label={`OpenRouter: ${usd(or.spentUsd)} de ${usd(or.capUsd)} este mes`}>
          <div className="row"><span>OpenRouter</span><span>{usd(or.spentUsd)} de ${or.capUsd}</span></div>
          <div className="bar"><i style={{ width: `${Math.min(100, ((or.spentUsd ?? 0) / or.capUsd) * 100)}%` }} /></div>
          <div className="row"><span>Por vídeo</span><span>{or.perVideoAvgUsd === null ? "sin dato" : usd(or.perVideoAvgUsd)} · tope {usd(or.perVideoCapUsd)}</span></div>
        </div>
      )}
      <div className="ver">{meta ? `versión ${meta.version}` : "conectando…"}</div>
    </nav>
  );
}
