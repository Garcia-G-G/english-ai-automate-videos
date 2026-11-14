import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronLeft, ChevronRight, Play, RotateCcw, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { approve, ApiFailure, reject, rerender } from "../api/client";
import type { ReviewItem, ReviewList, RejectRequest } from "../api/contract";
import { keys, useReview } from "../api/hooks";
import { confettiFrom } from "../components/Overlays";
import { SchedulePicker } from "../components/SchedulePicker";
import { usd, NA } from "../lib/format";
import { longLabel } from "../lib/schedule";
import { setBubi, toast } from "../lib/store";

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export function Revisar() {
  const q = useReview();
  const [idx, setIdx] = useState(0);
  const list = q.data;
  if (q.isError) return <div className="page"><div className="tile err">No pude leer Revisar: {(q.error as Error).message} <button className="lbtn" onClick={() => q.refetch()}>Reintentar</button></div></div>;
  const items = list?.items ?? [];
  const i = Math.min(idx, Math.max(0, items.length - 1));
  const item = items[i];
  const itemId = item?.id;
  useEffect(() => {
    document.getElementById("main")?.scrollTo({ top: 0, behavior: "smooth" });
  }, [itemId]);
  return (
    <div className="page">
      <header className="hd fade-up">
        <div>
          <div className="eyebrow">Revisar</div>
          <h1>{!list ? "Revisar" : items.length ? `${items.length} ${items.length === 1 ? "vídeo espera" : "vídeos esperan"} tu visto bueno` : "Nada que revisar"}</h1>
          {items.length > 0 && <p>Apruébalo con hora (se programa solo) o sin hora (queda en Por subir).</p>}
        </div>
        {items.length > 1 && (
          <div className="hd-r">
            <button className="chip" type="button" aria-label="Anterior" onClick={() => setIdx(Math.max(0, i - 1))} disabled={i === 0}><ChevronLeft size={14} /></button>
            <span className="chip">{i + 1} de {items.length}</span>
            <button className="chip" type="button" aria-label="Siguiente" onClick={() => setIdx(Math.min(items.length - 1, i + 1))} disabled={i >= items.length - 1}><ChevronRight size={14} /></button>
          </div>
        )}
      </header>
      {!list ? (
        <div className="rv"><div className="tile"><div className="skel" style={{ height: 560 }} /></div><div className="tile"><div className="skel" style={{ height: 560 }} /></div></div>
      ) : !item ? (
        <div className="tile empty enter"><img src="/bubi/bien_hecho.webp" alt="" /><b>Nada que revisar</b><span>Produce el siguiente en Inicio.</span></div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div key={item.id} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -60, rotate: -2 }} transition={{ type: "spring", stiffness: 260, damping: 24 }}>
            <ReviewCard item={item} list={list} after={items[i + 1]} />
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}

function ReviewCard({ item, list, after }: { item: ReviewItem; list: ReviewList; after: ReviewItem | undefined }) {
  const qc = useQueryClient();
  const [when, setWhen] = useState(list.schedule.next);
  const [whenOk, setWhenOk] = useState(true);
  const [plat, setPlat] = useState(() => list.platforms.filter((p) => p.enabled && p.mode === "auto").map((p) => p.key));
  const [title, setTitle] = useState(item.title);
  const [desc, setDesc] = useState(item.description);
  const [busy, setBusy] = useState<null | "sched" | "approve" | "reject" | "rerender">(null);
  const [rejecting, setRejecting] = useState(false);
  const [confirmRerender, setConfirmRerender] = useState(false);
  const [playing, setPlaying] = useState(false);
  const goBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => { setTitle(item.title); setDesc(item.description); setPlaying(false); }, [item.id, item.title, item.description]);

  const done = () => {
    void qc.invalidateQueries({ queryKey: keys.review });
    void qc.invalidateQueries({ queryKey: keys.home });
  };
  const doApprove = async (withTime: boolean) => {
    setBusy(withTime ? "sched" : "approve");
    try {
      const r = await approve(item.id, { publishAt: withTime ? when : null, platforms: plat, title, description: desc, hashtags: item.hashtags });
      confettiFrom(goBtn.current);
      setBubi("lo_lograste", 2400);
      const bad = r.results.filter((x) => !x.ok);
      toast(r.state === "scheduled" ? `✓ Programado para el <em>${esc(longLabel(r.publishAt!, list.schedule))}</em>` : "✓ Aprobado · <em>queda en Por subir</em>");
      if (bad.length) toast(`✕ ${esc(bad.map((b) => `${b.platform}: ${b.note ?? "falló"}`).join(" · "))}. Queda en Por subir.`, { tone: "bad", ms: 7000 });
      done();
    } catch (e) {
      toast(`✕ ${esc(e instanceof ApiFailure ? e.message : "No pude aprobarlo.")}`, { tone: "bad", ms: 6000 });
    } finally {
      setBusy(null);
    }
  };
  const doReject = async (reason: RejectRequest["reason"], note: string) => {
    setBusy("reject");
    try {
      await reject(item.id, { reason, note });
      toast("Rechazado. Lo anoté con el motivo.");
      done();
    } catch (e) {
      toast(`✕ ${esc(e instanceof ApiFailure ? e.message : "No pude rechazarlo.")}`, { tone: "bad" });
    } finally {
      setBusy(null);
      setRejecting(false);
    }
  };
  const doRerender = async () => {
    setBusy("rerender");
    try {
      await rerender(item.id);
      toast("↻ Volviendo a renderizar. Lo verás en Inicio.");
    } catch (e) {
      toast(`✕ ${esc(e instanceof ApiFailure ? e.message : "No pude empezar.")}`, { tone: "bad" });
    } finally {
      setBusy(null);
      setConfirmRerender(false);
    }
  };

  const passed = item.checks.filter((c) => c.ok === true).length;
  const failed = item.checks.filter((c) => c.ok === false).length;
  return (
    <div className="rv">
      <section className="tile rv-player enter" style={{ ["--i" as string]: 0 }}>
        <div className="rv-video">
          {playing && item.videoUrl ? (
            <video src={item.videoUrl} controls autoPlay playsInline />
          ) : (
            <>
              <img src={item.frame0.src2x ?? item.frame0.src} alt={`Fotograma 0 de ${item.title}`} />
              <span className="rv-f0">Fotograma 0 · lo que se ve en el feed</span>
              {item.videoUrl && <button type="button" className="rv-play" aria-label="Ver el vídeo" onClick={() => setPlaying(true)}><Play fill="currentColor" /></button>}
            </>
          )}
        </div>
        {item.strip.length > 0 && (
          <div className="rv-strip">
            {item.strip.map((s) => <figure key={s.label}><img src={s.src} alt="" loading="lazy" /><figcaption>{s.label}</figcaption></figure>)}
          </div>
        )}
      </section>

      <div className="rv-col">
        <section className={`tile hero enter${failed ? " failing" : ""}`} style={{ ["--i" as string]: 1 }}>
          <div className="verdict">
            <span className={`vbig${failed ? " bad" : ""}`} aria-hidden="true">{failed ? <X /> : <Check />}</span>
            <div style={{ minWidth: 0 }}>
              <div className="ey">{[item.typeLabel, item.design, item.items ? `${item.items} palabras` : null].filter(Boolean).join(" · ")}</div>
              <h2 className="vt">{item.title.replace(/\s#Shorts$/, "")}</h2>
              <p className="vsub">{failed ? `No pasa el control: ${item.gate.reason ?? `${failed} fallos`}` : `Pasa el control: ${passed} de ${item.checks.length}${passed < item.checks.length ? ", y lo demás sin dato" : ""}. Solo falta tu ojo.`}</p>
            </div>
          </div>
          <div className="checks">
            {item.checks.map((c) => (
              <div key={c.key} className={c.ok === true ? "ok" : c.ok === false ? "no" : "nd"}>
                <i aria-hidden="true">{c.ok === true ? "✓" : c.ok === false ? "✕" : "–"}</i>
                <div>{c.label}<small>{c.detail ?? NA}</small></div>
              </div>
            ))}
          </div>
        </section>

        <section className="tile enter" style={{ ["--i" as string]: 2 }}>
          <label className="fld"><span>Título <em>{title.length} de 100</em></span>
            <input value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} /></label>
          <label className="fld"><span>Descripción <em>generada · puedes editarla</em></span>
            <textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
          <div className="hashes">{item.hashtags.map((h) => <span key={h} className="tag">{h}</span>)}</div>
          <div className="plats" role="group" aria-label="Plataformas">
            {list.platforms.map((p) => (
              <label key={p.key} className={`plat${p.mode === "manual" ? " manual" : ""}`}>
                <input type="checkbox" role="switch" checked={plat.includes(p.key)} disabled={p.mode === "manual"}
                  onChange={(e) => setPlat((s) => (e.target.checked ? [...s, p.key] : s.filter((k) => k !== p.key)))} />
                <span className="sw" aria-hidden="true" />
                <b>{p.label}</b><small>{p.note}</small>
              </label>
            ))}
          </div>
        </section>

        <section className="tile enter" style={{ ["--i" as string]: 3 }}>
          <h3>¿Cuándo sale? <small>cualquier día y a cualquier hora</small></h3>
          <SchedulePicker info={list.schedule} value={when} onChange={(iso, ok) => { setWhen(iso); setWhenOk(ok); }} />
        </section>

        <div className="decide">
          <button ref={goBtn} type="button" className="gbtn ok" disabled={!!busy || !whenOk || plat.length === 0} aria-busy={busy === "sched"} onClick={() => doApprove(true)}>
            <Check aria-hidden="true" /> {busy === "sched" ? "Programando…" : "Aprobar y programar"}
          </button>
          <button type="button" className="gbtn alt" disabled={!!busy} aria-busy={busy === "approve"} onClick={() => doApprove(false)} title="Queda aprobado en Por subir, sin hora">
            <Check aria-hidden="true" /> {busy === "approve" ? "Aprobando…" : "Aprobar"}
          </button>
          <button type="button" className="lbtn no" disabled={!!busy} onClick={() => setRejecting((r) => !r)}><X size={15} aria-hidden="true" /> Rechazar</button>
          <button type="button" className="lbtn" disabled={!!busy} onClick={() => setConfirmRerender(true)}><RotateCcw size={15} aria-hidden="true" /> Volver a renderizar</button>
          <div className="cost"><b>{item.costUsd === null ? NA : usd(item.costUsd)}</b>lo que costó</div>
        </div>
        {rejecting && <RejectBox busy={busy === "reject"} onCancel={() => setRejecting(false)} onReject={doReject} />}
        {confirmRerender && (
          <div className="tile confirm fade-up">
            <b>¿Volver a renderizar este vídeo?</b> Cuesta unos {item.costUsd === null ? "$0.11" : usd(item.costUsd)} de voz y tarda ~2 min.
            <div className="actions"><button className="gbtn" type="button" onClick={doRerender} disabled={busy === "rerender"}>Sí, renderizar</button><button className="lbtn" type="button" onClick={() => setConfirmRerender(false)}>No</button></div>
          </div>
        )}
        {after && (
          <div className="tile nextup">
            <img src={after.frame0.src} alt="" />
            <div><b>Después:</b> {after.title.replace(/\s#Shorts$/, "")} <small>· pasa {after.checks.filter((c) => c.ok).length} de {after.checks.length}</small></div>
          </div>
        )}
      </div>
    </div>
  );
}

function RejectBox({ busy, onCancel, onReject }: { busy: boolean; onCancel: () => void; onReject: (r: RejectRequest["reason"], note: string) => void }) {
  const [reason, setReason] = useState<RejectRequest["reason"] | null>(null);
  const [note, setNote] = useState("");
  const opts: [RejectRequest["reason"], string][] = [["audio", "Audio"], ["imagen", "Imagen"], ["texto", "Texto"], ["otro", "Otro"]];
  return (
    <div className="tile confirm fade-up">
      <b>¿Por qué lo rechazas?</b>
      <div className="sched-row">{opts.map(([k, l]) => <button key={k} type="button" className={`pchip${reason === k ? " on" : ""}`} aria-pressed={reason === k} onClick={() => setReason(k)}>{l}</button>)}</div>
      <label className="fld"><span>Detalle <em>opcional</em></span><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Por ejemplo: la «e» de «bebé» suena «i»" /></label>
      <div className="actions"><button type="button" className="lbtn no" disabled={!reason || busy} onClick={() => reason && onReject(reason, note)}>Rechazar</button><button type="button" className="lbtn" onClick={onCancel}>Cancelar</button></div>
    </div>
  );
}
