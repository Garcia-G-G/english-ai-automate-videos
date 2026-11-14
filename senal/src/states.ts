const BG = "#05070f";

const style = document.createElement("style");
style.textContent = `
html,body{margin:0;height:100%;background:${BG};color:#dfe6ff;font-family:system-ui,sans-serif}
#senal-sweep{position:fixed;left:0;right:0;top:60%;height:1px;background:rgba(223,230,255,.12);overflow:hidden}
#senal-sweep::after{content:"";position:absolute;top:0;bottom:0;width:20%;background:linear-gradient(90deg,transparent,#dfe6ff,transparent);animation:senal-sweep 1.6s ease-in-out infinite}
@keyframes senal-sweep{from{left:-20%}to{left:100%}}
@media (prefers-reduced-motion:reduce){#senal-sweep::after{animation:none;left:40%}}
#senal-error{position:fixed;inset:0;display:grid;place-items:center;padding:0 16px;text-align:center;line-height:1.5}
`;
document.head.append(style);

/** Thin line sweeping on the ground plane; returns a stop function. */
export function showLoading(root: HTMLElement): () => void {
  const line = document.createElement("div");
  line.id = "senal-sweep";
  line.setAttribute("role", "status");
  line.setAttribute("aria-label", "Cargando");
  root.append(line);
  return () => line.remove();
}

export function showError(root: HTMLElement, message: string): void {
  const box = document.createElement("div");
  box.id = "senal-error";
  box.setAttribute("role", "alert");
  box.textContent = message; // textContent: the reason may carry server text
  root.replaceChildren(box);
}

/** One quiet line over the empty landscape when the chosen platform and period hold no videos. */
export function showEmpty(root: HTMLElement, message: string | null): void {
  root.querySelector("#senal-empty")?.remove();
  if (!message) return;
  const box = Object.assign(document.createElement("div"), { id: "senal-empty", textContent: message });
  box.setAttribute("role", "status");
  box.style.cssText = "position:fixed;inset:0;display:grid;place-items:center;padding:0 16px;text-align:center;pointer-events:none;opacity:.8";
  root.append(box);
}
