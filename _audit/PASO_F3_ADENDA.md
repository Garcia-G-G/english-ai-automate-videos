# F3 — adenda: dónde no acompaño el informe

Vistas P1 y P2 con mis propios ojos. `HEAD ad06c8c`.

**El salto es real.** Vivas, variadas, la tarjeta legible en las 12, y ninguna es el cuadro negro con lámpara. Es lo que el operador pidió.

Dos objeciones.

---

## 1 · "No seam on any of the 12" es demasiado fuerte

Tres se leen como una banda plana pegada encima, no como parte de la foto:

- `spanish_specific · V vs B sounds` — franja azul con bordes duros contra la terracota
- `travel · boarding pass` — franja turquesa plana
- `business · meetings and agendas` — franja gris que cruza entera

No es fatal: en las tres se puede leer como desenfoque. Pero **la afirmación es más rotunda que la evidencia**, y esto lo decide el ojo del operador, no el mío ni el tuyo. Que las mire.

Las otras nueve: de acuerdo, la banda desaparece dentro de la imagen.

---

## 2 · P2 no dibujó el watermark ni la barra — y ahí es donde se movió el riesgo

**Esto sí es un defecto, y lo creamos nosotros en este mismo paso.**

El diseño anterior mandaba el brillo a los tercios superior e inferior para dejar el centro oscuro. F3 mantiene esa forma y **sube el brillo**. Y el watermark `learningroutes.com` es **texto blanco que vive en el tercio inferior**.

Los frames de P2 no lo llevan. Tampoco la barra de progreso. Así que la parte del cuadro que más cambió es justamente la que no se probó.

Luminancia media bajo el watermark, sobre las 12 imágenes nuevas (0 = negro, 255 = blanco). El texto es blanco: **cuanto más alto, menos se ve**:

| imagen | luminancia | |
|---|---|---|
| `rainbow_colors` | **198.1** | blanco sobre casi-blanco |
| `boarding_pass` | 158.7 | |
| `silent_letters` | 158.3 | |
| `a_sweet_tooth` | 145.6 | límite |
| `v_vs_b_sounds` | 124.9 | límite |
| … las otras 7 | 82 – 113 | bien |

*Salvedad honesta: no pude importar `watermark_bounds()` en este entorno (falta `pydantic`), así que usé una caja estimada a partir de un frame real. Los números son indicativos, no autoritativos. La dirección no depende de la caja: el tercio inferior es ahora claro por diseño.*

### Y la razón por la que nadie lo detectó

```
grep watermark src/text_contrast.py src/qa_gate.py
→ (nada)
```

**El gate no mide el watermark.** Nunca lo ha medido. Mide la tarjeta del titular y solo eso.

> ### Ceguera del techo, tercera instancia — y esta la fabricamos nosotros
>
> 1. El gate puntuaba mejor cuando no había imagen.
> 2. El gate premiaba que la imagen fuera negra, así que el prompt la pedía negra.
> 3. **Movimos el brillo al tercio inferior para arreglar (2), y ahí vive texto blanco que el gate no mira.**
>
> Las tres veces: el instrumento cubría una parte del cuadro y la decisión se tomó como si cubriera el cuadro entero.

---

## Lo que hay que añadir a (d)

**Antes de dar F3 por cerrado:**

- **Re-render de P2 con el pipeline completo** — `finalize_frame`, watermark y barra incluidos. Es la prueba que faltaba, y sobre las mismas 12 imágenes ya pagadas: **coste cero**.
- **El watermark necesita su propio suelo.** El mismo mecanismo del scrim, local: un degradado suave detrás de la marca, determinista, con la geometría de `watermark_bounds()`. No subir opacidad global ni oscurecer la imagen entera — eso deshace F3.
- **El gate mide el watermark.** Añadir su caja a `text_contrast`. Sin esto vuelve: es la tercera vez que el instrumento mira menos de lo que decide.
- La barra de progreso, lo mismo: comprobar, y si hace falta, suelo propio.

## Y no te saltes (d)

Los dos `food_restaurant` los declaraste, y el razonamiento de por qué colisionan es correcto. Pero **"still look different" es generoso**: las dos son cajas de cítricos y se leen como hermanas. Con `social` saliendo 6 veces en el historial, sin memoria esto va a pasar seguido.

El espacio (5120) no es el problema, como dijiste. La selección sin memoria sí.
