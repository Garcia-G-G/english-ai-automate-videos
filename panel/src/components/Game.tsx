import { useEffect, useState } from "react";
import type { Achievement, Game } from "../api/contract";

/** Level, XP bar, streak and the last three achievements. Opens the full sheet. */
export function XPStrip({ game, fresh }: { game: Game; fresh: string | null }) {
  const [open, setOpen] = useState(false);
  const unlocked = game.achievements.filter((a) => a.unlockedAt).sort((a, b) => (a.unlockedAt! < b.unlockedAt! ? 1 : -1));
  const pct = Math.max(0, Math.min(100, (game.levelXp / game.levelSize) * 100));
  return (
    <>
      <button type="button" className="tile xp" onClick={() => setOpen(true)} aria-label={`Nivel ${game.level}, ${game.levelXp} de ${game.levelSize} XP, racha de ${game.streakDays} días. Ver logros`}>
        <span className="lv">NV {game.level}</span>
        <span className="bar" aria-hidden="true"><i style={{ width: `${pct}%` }} /></span>
        <span className="st">{game.levelXp} / {game.levelSize} XP</span>
        <span className="st">Racha <b>{game.streakDays}</b> {game.streakDays === 1 ? "día" : "días"}</span>
        <span className="ach" aria-hidden="true">
          {unlocked.slice(0, 3).reverse().map((a) => <span key={a.id} className={a.id === fresh ? "new" : ""} title={a.name}>{a.emoji}</span>)}
        </span>
      </button>
      {open && <AchievementsSheet list={game.achievements} onClose={() => setOpen(false)} />}
    </>
  );
}

const fmtDate = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", timeZone: "America/Costa_Rica" });

export function AchievementsSheet({ list, onClose }: { list: Achievement[]; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, [onClose]);
  const done = list.filter((a) => a.unlockedAt).length;
  return (
    <div className="sheet-scrim" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="ach-t">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <h2 id="ach-t">Logros · {done} de {list.length}</h2>
          <button type="button" className="lbtn" onClick={onClose} autoFocus>Cerrar</button>
        </div>
        <div className="achgrid">
          {list.map((a) => (
            <div key={a.id} className={`achc${a.unlockedAt ? "" : " locked"}`}>
              <span className="e" aria-hidden="true">{a.emoji}</span>
              <div>
                <b>{a.name}</b>
                <small>{a.description}</small>
                <small>{a.unlockedAt ? `Desde el ${fmtDate.format(new Date(a.unlockedAt))}` : "Aún no"}</small>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
