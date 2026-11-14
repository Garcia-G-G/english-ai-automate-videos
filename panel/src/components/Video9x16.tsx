import type { Family, Thumb } from "../api/contract";

const FAMILY: Record<Family, [string, string]> = {
  casa: ["#FF7A59", "#D43B59"], comida: ["#3DB36B", "#1F7A4D"], cuerpo: ["#9B6BE8", "#6A3CB8"], animales: ["#2BB5A8", "#157A78"],
  ropa: ["#4C9BF0", "#2459B5"], ciudad: ["#6C7BE8", "#3B3FA8"], emociones: ["#F06BB0", "#B8307F"], clima: ["#4FB6F2", "#1B76B8"],
  vida: ["#2E4A8A", "#13234F"], reto: ["#F5B82E", "#D9822B"], test: ["#FF8A5B", "#E0533A"],
};

/**
 * The video's own frame 0 — never restyled, it is the Tablero look of the Short.
 * Until the engine has drawn it (STEP 85b), a placeholder in the topic's family
 * colours says so with a small badge.
 */
export function Video9x16({ thumb, family, emoji, topic, width = 150 }: { thumb: Thumb | null; family: Family | null; emoji: string; topic: string; width?: number }) {
  if (thumb) {
    return (
      <div className="v9" style={{ width, backgroundImage: thumb.placeholder ? `url(${thumb.placeholder})` : undefined, backgroundSize: "cover" }}>
        <img className="fr" src={thumb.src} srcSet={thumb.src2x ? `${thumb.src} 1x, ${thumb.src2x} 2x` : undefined} alt={`Fotograma 0 de ${topic}`} loading="lazy" decoding="async" />
      </div>
    );
  }
  const [a, b] = FAMILY[family ?? "animales"];
  return (
    <div className="v9 drawn" style={{ width, background: `linear-gradient(180deg, ${a}, ${b})` }} role="img" aria-label={`Vista previa de ${topic}`}>
      <div className="h"><span>¿CÓMO SE DICE?</span></div>
      <div className="c">{emoji} {topic}</div>
      <div className="t">{Array.from({ length: 8 }, (_, i) => <i key={i} />)}</div>
      <img className="bubi-in" src="/bubi/wow.webp" alt="" aria-hidden="true" />
      <span className="badge">vista previa</span>
    </div>
  );
}
