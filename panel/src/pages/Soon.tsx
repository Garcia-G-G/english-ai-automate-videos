import type { Meta } from "../api/contract";

/** A page not rebuilt yet: says so and sends Garcia to the same page in the old panel. */
export function Soon({ title, what, meta }: { title: string; what: string; meta: Meta | undefined }) {
  return (
    <div className="page">
      <div className="tile soon enter">
        <img src="/bubi/wow.webp" alt="" />
        <h2>{title}, muy pronto aquí</h2>
        <p>{what} Mientras tanto sigue en el panel de siempre.</p>
        {meta && <a className="lbtn" href={meta.streamlitUrl} target="_blank" rel="noreferrer">Abrir el panel de siempre</a>}
      </div>
    </div>
  );
}
