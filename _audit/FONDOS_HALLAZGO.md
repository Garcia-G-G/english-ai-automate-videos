# El fondo generado es negro por diseño — y el gate lo premia

**Encontrado verificando D0**, mirando el frame que pedí como prueba. `HEAD b187ec3`.

---

## Lo que pediste

> *"un fondo lindo como los vistosos de antes no pasa nada por el precio pero prefiero eso que estos solo de colores"*

## Lo que se genera

La imagen que pagaste ($0.041) para `V vs B sounds`: un interior nocturno donde **el 60 % del cuadro es negro puro**. Una lámpara arriba a la izquierda, un vaso abajo. Nada más.

No es que el render la aplaste — **la imagen original ya viene así**. La comparé: fuente y frame renderizado son igual de oscuros. El defecto está aguas arriba del renderer, en el prompt.

---

## La causa, en `src/topic_background.py`

Todas las instrucciones piden oscuridad. Todas.

**Los 11 escenarios por categoría** (`CATEGORY_SCENES`, `:88-100`):

| categoría | escena |
|---|---|
| business | "a **dark** modern office **after hours**" |
| travel | "a **dimly lit** airport terminal **at night**" |
| social | "a **low-lit** bar table" |
| daily_life | "a kitchen counter **at night**" |
| idioms | "a worn wooden table … **in low light**" |
| phrasal_verbs | "a cluttered desk **in a dark room**" |
| false_friends | "two objects … on a **shadowed** surface" |
| common_mistakes | "an open notebook … on a **dark** desk" |
| kids_animals | "a quiet room **at dusk**" |
| food | "a **dark** table set with plates" |
| technology | "a **dark** room with a screen glow" |

**11 de 11.** Y el `DEFAULT_SCENE`:

> "a quiet interior at night, one warm light source, **most of the frame in shadow**"

Y el bloque `EXPOSURE`, que va idéntico en cada prompt:

> "The centre of the frame is in **deep shadow** across a wide horizontal band … **rich dark tones**"

Siete instrucciones independientes pidiendo lo mismo. El modelo obedece.

### Y el video de la prueba cayó en el peor caso

`spanish_specific` **no está** en `CATEGORY_SCENES`. Se fue al `DEFAULT_SCENE` — el único que dice literalmente *"most of the frame in shadow"*.

No es un caso raro:

| | |
|---|---|
| categorías reales en `content/topics/` | **20** |
| con escena propia | 9 |
| **que caen al DEFAULT_SCENE** | **11** |

Los 11: `confusing_words`, `cultural`, `everyday_expressions`, `food_restaurant`, `grammar`, `kids_colors`, `kids_numbers`, `pronunciation`, `slang`, `spanish_specific`, `work_office`.

**Más de la mitad de tu contenido pide el escenario más oscuro del fichero.**

Y dos escenas huérfanas que ninguna categoría usa: `daily_life` y `food`. Las reales se llaman `everyday_expressions` y `food_restaurant`. El diccionario se escribió de memoria, no leyendo `content/topics/`.

---

## Por qué pasó, y es lo interesante

El comentario del propio módulo lo explica sin darse cuenta:

> *"a sunset or a cloudscape puts its brightest region across the middle of the frame, which is exactly where the card sits. So every prompt here pins the exposure … as an instruction rather than a hope, and then the gate checks it anyway."*

El prompt **se escribió para pasar el gate de contraste**. Y el gate premia la oscuridad: cuanto más negra la imagen, mejor la puntuación. Este video sacó **14.882:1** contra un suelo de 4.5 — porque el fondo casi no existe.

> ### La puerta mide lo contrario del objetivo
>
> El gate mide legibilidad y **sube cuando el fondo desaparece**. Tu objetivo declarado era un fondo vistoso. De los dos, **solo uno está medido**, y el prompt se optimizó contra el medido.
>
> Es la ceguera del techo otra vez, pero un nivel más arriba: antes el gate no distinguía "sin imagen"; ahora es la razón por la que la imagen se pide negra.

El arreglo anterior (bajar `RENDER_OVERLAY_OPACITY` 0.35 → 0.10, zoom a 1.0) fue **correcto y no basta**: quitó el aplastamiento del renderer sobre una imagen que ya nacía aplastada.

---

## La salida que propongo

**Separar las dos cosas que el prompt mezcla.** Hoy pide "escena oscura" *y* "banda oscura en el centro" como si fueran una. Son separables:

1. **El prompt pide una imagen viva.** Colorida, con luz, con sitio. Se le quita "dark/night/dim/shadow" de los escenarios y del `EXPOSURE`.
2. **La banda oscura se compone después, en código.** Un degradado sobre la franja donde va la tarjeta, con la geometría que ya está en `config/layout.py`. Determinista.

Con eso el contraste queda **garantizado por construcción**, no por rezarle al generador y comprobarlo luego. Y el gate vuelve a ser lo que debía ser — una red de seguridad — en vez del que decide cómo se ve el canal.

Coste: el mismo. Es el mismo número de imágenes.

**Y hay que rellenar las 11 categorías sin escena**, más arreglar las dos huérfanas.

### El riesgo, dicho antes

Una imagen viva con una banda compuesta encima puede verse **peor** que una oscura: la costura del degradado se nota si el scrim es duro. Se resuelve con un degradado suave y sobrado por arriba y por abajo, pero es trabajo visual y hay que verlo en frames, no razonarlo.

**Y esto no lo puede juzgar el gate.** Lo tienes que mirar tú. La prueba de este paso son imágenes, no un número.
