# Biblioteca de clips por personaje (CharacterDirector)

El renderer v2 (kids) ya no reproduce clips al azar: `src/video/v2/character_director.py`
elige el clip según lo que hace la narración en cada momento, usando los
word-timestamps del audio.

## Estructura de carpetas

```
assets/clips/<perfil>/<personaje>/
    talking/     ← narración activa (la mayor parte del video)
    idle/        ← pausas de la voz (>1.2s de silencio)
    reaction/    ← arranque de un grupo con palabra EN clave (sorpresa/curiosidad)
    celebrate/   ← CTA final ("¡Sígueme para más!")
```

También se acepta el sufijo en el nombre: `momo-ventana-talking.mp4` en la
raíz del personaje se clasifica como `talking`.

Reglas del director:
- Cambia de clip solo en fronteras de estado o cada ~5s (corte en beats,
  ajustado a huecos entre palabras — nunca a mitad de palabra si se puede).
- Nunca repite el mismo clip dos veces seguidas si hay alternativa.
- Fallback si una categoría está vacía: `talking → idle → reaction → celebrate`
  (y viceversa según el estado); nunca crashea.

## Cuántos clips generar

| Categoría  | Mínimo | Ideal | Duración por clip |
|------------|--------|-------|-------------------|
| talking    | 2      | 4-6   | 6-8s (se loopean) |
| idle       | 1      | 2-3   | 5-6s              |
| reaction   | 1      | 2-3   | 3-4s              |
| celebrate  | 1      | 2     | 4-5s              |

Formato: MP4 vertical u horizontal (se recorta al centro), 24-30fps.
La ventana kids muestra ~848x628px — genera a 720p o más.

## Prompts para Google Flow — MOMO (panda rojo, kids)

Prefijo común para consistencia (añádelo a todos):
> *Pixar-style 3D animation, cute red panda "Momo", big expressive eyes,
> soft warm lighting, cozy forest clearing background, gentle camera,
> no text, no captions, seamless loopable motion.*

### talking/ (6-8s c/u)
1. "Momo looking directly at camera, mouth moving as if narrating a story,
   gentle head bobs and small paw gestures, friendly engaged expression,
   subtle blinking, calm loopable rhythm."
2. "Momo explaining something to the viewer, counting on his fingers,
   nodding slowly while talking, warm teacher energy, ears twitching
   slightly, continuous natural talking motion."
3. "Momo talking to camera while tilting his head side to side with
   curiosity, small hand gestures as if telling a secret, soft smile
   between phrases."
4. "Momo sitting on a tree stump talking animatedly to camera, gesturing
   with both paws open, enthusiastic but gentle, tail swaying slowly."

### idle/ (5-6s c/u)
5. "Momo calmly listening, looking at camera with a soft smile, slow
   breathing, occasional blink and ear twitch, tail curled around his
   feet, almost still, perfect idle loop."
6. "Momo waiting patiently, looking around with mild curiosity, then back
   to camera, relaxed posture, tiny nose wiggle, loopable."

### reaction/ (3-4s c/u)
7. "Momo suddenly surprised and delighted, eyes widening, ears perking up,
   small excited hop, paws to cheeks, then settling with a big smile —
   a short 'wow' reaction, no sound."
8. "Momo having a lightbulb moment: gasps, points upward with one paw,
   excited nodding as if saying 'that's the word!', bright curious eyes."

### celebrate/ (4-5s c/u)
9. "Momo celebrating happily, jumping and clapping his paws, confetti
   falling around him, big joyful smile, waving goodbye to camera at the
   end, festive but soft colors."
10. "Momo doing a happy little dance, swaying side to side with arms up,
    then a thumbs-up to camera with a wink, celebratory sparkles."

## Prompts — LILA (luciérnaga, kids)

Prefijo: *Pixar-style 3D animation, tiny cute firefly "Lila" with a warm
golden glow, translucent wings, big friendly eyes, twilight garden
background, magical soft light, no text, loopable.*

- talking: "Lila hovering at camera height, glowing softly in rhythm with
  her speech, tiny hand gestures, wings shimmering, bobbing gently."
- idle: "Lila floating in place, slow glow pulse like breathing, looking
  around dreamily, wings fluttering slowly."
- reaction: "Lila flashing bright with excitement, quick loop-the-loop in
  the air, sparkle trail, delighted expression."
- celebrate: "Lila drawing a glowing heart in the air with her light
  trail, then waving both arms happily at camera."

## Prompts — CAPI (capibara, adults)

Prefijo: *Pixar-style 3D animation, chill capybara "Capi" wearing round
glasses, modern minimal studio with warm desk lamp, sophisticated muted
colors, subtle motion, no text, loopable.*

- talking: "Capi at a desk talking to camera like a friendly professor,
  calm mouth movement, occasional paw gesture over an open notebook,
  relaxed confident energy."
- idle: "Capi sipping mate slowly, looking at camera with a serene smile,
  slow blink, steam rising from the cup."
- reaction: "Capi raising his eyebrows over his glasses, intrigued nod,
  small approving smile — a subtle 'interesting!' reaction."
- celebrate: "Capi giving a slow satisfied thumbs-up and a nod to camera,
  confetti minimal and elegant, warm smile."

## Flujo de trabajo

1. Genera los clips en Google Flow con los prompts de arriba.
2. Descárgalos y colócalos en la subcarpeta correcta
   (`assets/clips/kids/momo/talking/`, etc.). El nombre del archivo da igual
   si está en subcarpeta; si lo dejas en la raíz usa sufijo `-talking` etc.
3. No hace falta tocar código ni config: el director re-escanea la
   biblioteca en cada render.
4. Los 2 clips actuales de Momo lanzando lodo quedaron en
   `kids/momo/reaction/` (sirven de reacción hasta tener los definitivos).
