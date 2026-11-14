import { useRef, useState } from "react";
import { Play, Check, RotateCcw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { produce, ApiFailure } from "../api/client";
import { STEPS, type Game, type Home, type Meta, type StepKey } from "../api/contract";
import { keys, useGame, useHome } from "../api/hooks";
import { AreaChart, CountUp } from "../components/Charts";
import { XPStrip } from "../components/Game";
import { confettiFrom } from "../components/Overlays";
import { ThemeChip } from "../components/ThemeChip";
import { Video9x16 } from "../components/Video9x16";
import type { ThemeMode } from "../design/theme";
import type { ThemeName } from "../api/contract";
import { useServerEvent } from "../lib/events";
import { change, greeting, n, NA, todayLabel, usd } from "../lib/format";
import { setBubi, toast } from "../lib/store";

interface Props { meta: Meta | undefined; theme: ThemeName; mode: ThemeMode; until: string; setMode: (m: ThemeMode) => void }

export function Inicio({ meta, theme, mode, until, setMode }: Props) {
  const home = useHome();
  const game = useGame();
  const [fresh, setFresh] = useState<string | null>(null);
  useServerEvent((e) => {
    if (e.type === "achievement.unlocked") {
      setFresh(e.achievement.id);
      setBubi("bien_hecho", 2600);
      toast(`🏆 Logro nuevo: <em>${escapeHtml(e.achievement.name)}</em>`, { ms: 3200 });
      confettiFrom(document.querySelector(".xp .ach"));
    }
  });
  const h = home.data;
  const g = game.data;
  const stale = meta?.statsReadAt ? (Date.now() - new Date(meta.statsReadAt).getTime()) / 3.6e6 : null;
  return (
    <div className="page">
      <header className="hd fade-up">
        <div>
          <div className="eyebrow">{g ? `Nivel ${g.level} · día ${g.streakDays} de racha` : todayLabel()}</div>
          <h1>{greeting()}, {meta?.ownerName ?? "Garcia"}</h1>
          <p>{h ? h.daySentence : <span className="skel" style={{ display: "inline-block", width: 380, height: 14 }} />}</p>
        </div>
        <div className="hd-r">
          {meta?.mock && <span className="chip demo">Datos de ejemplo</span>}
          <ThemeChip theme={theme} mode={mode} until={until} setMode={setMode} />
          <span className="chip"><span className={`dot${stale !== null && stale > 24 ? " warn" : ""}`} />
            {stale === null ? "Estadísticas: sin dato" : stale < 1 ? "Estadísticas al día" : `Estadísticas · hace ${Math.round(stale)} h`}</span>
        </div>
      </header>

      {g ? <XPStrip game={g} fresh={fresh} /> : game.isError ? null : <div className="skel" style={{ height: 56, borderRadius: 18 }} />}

      {home.isError ? (
        <div className="tile err">No pude leer Inicio: {(home.error as Error).message} <button className="lbtn" onClick={() => home.refetch()}><RotateCcw size={14} /> Reintentar</button></div>
      ) : (
        <div className="grid-home">
          <div className="a-hero"><Hero home={h} game={g} /></div>
          <div className="a-agenda"><AgendaTile home={h} /></div>
          <div className="a-views"><ViewsTile home={h} /></div>
          <div className="a-formats"><FormatsTile home={h} /></div>
          <div className="a-sequels"><SequelsTile home={h} /></div>
        </div>
      )}
    </div>
  );
}

/** «bv045_carro» → «CARRO»: a script id shown as its topic, until the API sends the topic itself. */
const scriptLabel = (s: string) => (/^[a-z]{2,4}\d{2,4}_/.test(s) ? s.replace(/^[a-z]{2,4}\d{2,4}_/, "").replace(/_/g, " ").toUpperCase() : s);
const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const EMPTY_STEPS: Record<StepKey, number> = { guion: 0, voz: 0, montaje: 0, sonido: 0, control: 0 };

function Hero({ home, game }: { home: Home | undefined; game: Game | undefined }) {
  const qc = useQueryClient();
  const btn = useRef<HTMLButtonElement>(null);
  const [job, setJob] = useState<{ id: string; steps: Record<StepKey, number>; state: "running" | "done" } | null>(null);
  useServerEvent((e) => {
    if (!job) return;
    if (e.type === "job.step" && e.jobId === job.id) setJob((j) => (j ? { ...j, steps: { ...j.steps, [e.step]: e.progress } } : j));
    if (e.type === "job.done" && e.jobId === job.id) {
      setJob((j) => (j ? { ...j, state: "done", steps: { guion: 1, voz: 1, montaje: 1, sonido: 1, control: 1 } } : j));
      setBubi("lo_lograste", 2800);
      confettiFrom(btn.current);
      toast(`✓ Listo · <em>te espera en Revisar</em>${e.xpGained ? ` · +${e.xpGained} XP` : ""}`);
      setTimeout(() => setJob(null), 2600);
    }
    if (e.type === "job.failed" && e.jobId === job.id) {
      setJob(null);
      setBubi("idle");
      toast(`✕ No se pudo producir: ${escapeHtml(e.reason)}`, { tone: "bad", ms: 6000 });
    }
  });
  if (!home) return <div className="tile hero enter" style={{ minHeight: 300 }}><div className="skel" style={{ height: 260 }} /></div>;
  const nx = home.next;
  if (!nx) {
    return (
      <div className="tile hero enter">
        <div className="empty"><img src="/bubi/bien_hecho.webp" alt="" /><b>La cola está vacía</b><span>Añade guiones en Temas o crea uno en Crear.</span></div>
      </div>
    );
  }
  const go = async () => {
    try {
      setBubi("wow");
      const r = await produce(nx.scriptId);
      setJob({ id: r.jobId, steps: { ...EMPTY_STEPS }, state: "running" });
      toast(`▶ En marcha: <em>${escapeHtml(nx.topic)}</em>${r.etaS ? ` · listo en ~${Math.max(1, Math.round(r.etaS / 60))} min` : ""}`);
      void qc.invalidateQueries({ queryKey: keys.meta });
    } catch (err) {
      setBubi("idle");
      toast(`✕ ${escapeHtml(err instanceof ApiFailure ? err.message : "No pude empezar el vídeo.")}`, { tone: "bad", ms: 6000 });
    }
  };
  const [before, after] = splitTopic(nx.title, nx.topic);
  const f = nx.facts;
  return (
    <section className="tile hero lift enter" style={{ ["--i" as string]: 0 }} aria-labelledby="next-t">
      <div className="hero-in">
        <Video9x16 thumb={nx.thumb} family={nx.family} emoji={nx.emoji} topic={nx.topic} />
        <div style={{ minWidth: 0 }}>
          <div className="ey">Siguiente vídeo{nx.slot ? ` · sale a las ${nx.slot}` : ""}</div>
          <h2 id="next-t">{before}<span className="mark">{nx.topic}</span>{after}{nx.emoji && !nx.title.includes(nx.emoji) ? <> <span aria-hidden="true">{nx.emoji}</span></> : null}</h2>
          <div className="tags">{nx.tags.map((t) => <span key={t.label} className={`tag ${t.tone}`}>{t.label}</span>)}</div>
          <div className="words" aria-label="Palabras en inglés">{nx.words.map((w) => <span key={w}>{w}</span>)}</div>
          {job ? (
            <div className="steps" aria-label="Progreso">
              {STEPS.map((s) => (
                <div key={s.key} className={job.steps[s.key] >= 1 ? "ok" : ""}><i><b style={{ width: `${job.steps[s.key] * 100}%` }} /></i>{s.label}</div>
              ))}
            </div>
          ) : (
            <div className="facts">
              <div><Fact v={f.durationS} fmt={(v) => `~${v} s`} />duración</div>
              <div><Fact v={f.costUsd} fmt={(v) => `~${usd(v)}`} />costo</div>
              <div><Fact v={f.renderMin} fmt={(v) => `~${v} min`} />render</div>
              <div><Fact v={f.repeated} fmt={(v) => `${v}/${nx.words.length}`} />repetidas</div>
            </div>
          )}
          <div className="actions">
            <button ref={btn} type="button" className={`gbtn${job?.state === "done" ? " done" : ""}`} aria-busy={job?.state === "running"} onClick={go} disabled={!!job}>
              {job?.state === "done" ? <><Check aria-hidden="true" /> Listo · en Revisar</> : job ? "En marcha…" : <><Play aria-hidden="true" fill="currentColor" /> Producir{game && typeof nx.xp === "number" ? ` · +${nx.xp} XP` : ""}</>}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Fact({ v, fmt }: { v: number | null; fmt: (v: number) => string }) {
  return v === null ? <b className="na">{NA}</b> : <b>{fmt(v)}</b>;
}

function splitTopic(title: string, topic: string): [string, string] {
  const i = title.indexOf(topic);
  return i < 0 ? [`${title} `, ""] : [title.slice(0, i), title.slice(i + topic.length)];
}

function AgendaTile({ home }: { home: Home | undefined }) {
  if (!home) return <div className="tile enter" style={{ minHeight: 300 }}><div className="skel" style={{ height: 240 }} /></div>;
  const a = home.agenda;
  const nextFree = a.today.findIndex((s) => s.state === "free");
  return (
    <section className="tile agenda lift enter" style={{ ["--i" as string]: 1 }} aria-labelledby="ag-t">
      <h3 id="ag-t">Agenda de hoy <small>Costa Rica</small></h3>
      {a.today.map((s, i) => (
        <div key={s.time} className={`slot ${s.state}${i === nextFree ? " next" : ""}`}>
          <span className="hh">{s.time}</span>
          <span className="dot" aria-hidden="true" />
          <div className="bx">
            {s.state === "free" ? (
              <><span className="em" aria-hidden="true">＋</span><b>Libre</b><span className="rest">{s.fillsWith ? `· lo llena ${scriptLabel(s.fillsWith)}` : "· sin guion"}</span></>
            ) : (
              <><span className="em" aria-hidden="true">{s.emoji ?? "▶"}</span><b>{s.title}</b>
                <span className="rest">{s.state === "published" ? (s.views === null ? "· publicado" : `· ${n(s.views)}`) : "· programado"}</span></>
            )}
          </div>
        </div>
      ))}
      <div className="foot">Mañana: {a.tomorrow.slots} huecos · {a.tomorrow.scripted >= a.tomorrow.slots ? "ya hay guion para todos" : `guion para ${a.tomorrow.scripted}`}</div>
    </section>
  );
}

function ViewsTile({ home }: { home: Home | undefined }) {
  if (!home) return <div className="tile enter" style={{ minHeight: 320 }}><div className="skel" style={{ height: 280 }} /></div>;
  const v = home.views;
  if (!v) return (
    <section className="tile enter" style={{ ["--i" as string]: 2 }} aria-labelledby="vw-t">
      <h3 id="vw-t">Vistas</h3>
      <p>sin dato: pulsa «Actualizar estadísticas».</p>
    </section>
  );
  const ch = change(v.views, v.prevViews);
  return (
    <section className="tile lift enter" style={{ ["--i" as string]: 2 }} aria-labelledby="vw-t">
      <h3 id="vw-t">Vistas · {v.periodDays === 28 ? "4 semanas" : `${v.periodDays} días`} {ch && <small>{ch.label} vs las {v.periodDays === 28 ? "4" : ""} anteriores</small>}</h3>
      <div className="vrow">
        <span className="big"><CountUp to={v.views} /></span>
        {ch && <span className={`pill${ch.down ? " down" : ""}`}>{ch.down ? "▼" : "▲"} {ch.label}</span>}
      </div>
      <AreaChart data={v.daily} height={140} />
      <div className="mini3">
        <div><b><CountUp to={v.totals.views} /></b>en total</div>
        <div><b><CountUp to={v.totals.subs} /></b>suscriptores</div>
        <div><b><CountUp to={v.totals.likes} /></b>me gusta</div>
      </div>
    </section>
  );
}

function FormatsTile({ home }: { home: Home | undefined }) {
  if (!home) return <div className="tile enter" style={{ minHeight: 200 }}><div className="skel" style={{ height: 160 }} /></div>;
  const top = home.formats[0]?.median ?? 1;
  return (
    <section className="tile lift enter" style={{ ["--i" as string]: 3 }} aria-labelledby="fm-t">
      <h3 id="fm-t">¿Qué formato rinde? <small>vistas típicas</small></h3>
      {home.formats.map((f, i) => (
        <div key={f.key} className="fr" title={`${f.videos} vídeos`}>
          <span>{f.label}</span>
          <div className="tr"><i style={{ width: `${(f.median / top) * 100}%`, backgroundColor: f.color, ["--i" as string]: i }} /></div>
          <span className="v">{n(Math.round(f.median))}</span>
        </div>
      ))}
      {home.formatsNote && <div className="fnote">{home.formatsNote}</div>}
    </section>
  );
}

function SequelsTile({ home }: { home: Home | undefined }) {
  if (!home || home.sequels.length === 0) return null;
  return (
    <section className="tile lift enter" style={{ ["--i" as string]: 4 }} aria-labelledby="sq-t">
      <h3 id="sq-t">Secuelas por escribir <small>pasaron de 800 vistas</small></h3>
      {home.sequels.map((s) => (
        <div key={s.topic} className="seqrow">
          <span className="em" aria-hidden="true">{s.emoji || "★"}</span>
          <div><b>{s.topic}</b><small>el original: {n(s.parentViews)} vistas</small></div>
        </div>
      ))}
    </section>
  );
}
