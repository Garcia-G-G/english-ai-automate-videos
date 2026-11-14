import { bubiStore, reducedMotion, toastStore, useStore } from "../lib/store";

const BUBI_SRC: Record<string, string> = {
  idle: "/bubi/simbolo.webp",
  wow: "/bubi/wow.webp",
  lo_lograste: "/bubi/lo_lograste.webp",
  bien_hecho: "/bubi/bien_hecho.webp",
};

/** Bubi lives in the bottom-right corner and reacts to what happens. Decorative. */
export function BubiCorner() {
  const { mood, celebrate } = useStore(bubiStore);
  return (
    <img
      key={`${mood}-${celebrate}`}
      className={`bubi-nav${mood === "lo_lograste" || mood === "bien_hecho" ? " celebrate" : ""}`}
      src={BUBI_SRC[mood]}
      alt=""
      aria-hidden="true"
      width={74}
      height={74}
    />
  );
}

export function Toasts() {
  const list = useStore(toastStore);
  return (
    <div className="toasts" role="status" aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className={`toast${t.tone === "bad" ? " bad" : ""}${t.leaving ? " leave" : ""}`} dangerouslySetInnerHTML={{ __html: t.html }} />
      ))}
    </div>
  );
}

const COLORS = ["#FFD23F", "#FF4F8B", "#4BE3A0", "#7B5CFF", "#2BD9C7"];
/** 34 pieces of confetti from an element, then they clean themselves up. */
export function confettiFrom(el: Element | null) {
  if (!el || reducedMotion()) return;
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top;
  for (let i = 0; i < 34; i++) {
    const c = document.createElement("i");
    c.className = "confetti";
    c.style.left = `${x}px`;
    c.style.top = `${y}px`;
    c.style.background = COLORS[i % COLORS.length] ?? "#FFD23F";
    const ang = Math.random() * Math.PI - Math.PI;
    const dist = 90 + Math.random() * 170;
    c.style.setProperty("--dx", `${Math.cos(ang) * dist}px`);
    c.style.setProperty("--dy", `${Math.sin(ang) * dist + 60}px`);
    c.style.setProperty("--r", `${Math.random() * 720 - 360}deg`);
    document.body.appendChild(c);
    setTimeout(() => c.remove(), 1400);
  }
}
