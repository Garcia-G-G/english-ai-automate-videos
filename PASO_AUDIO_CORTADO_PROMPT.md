# Paso: el audio se oye cortado

## 0. La versión de UNA LÍNEA de lo que pidió el dueño

> "estoy empezando a escuchar más los audios de los videos no sé porque se escucha como cortado antinatural"

**Que el audio no suene a cinta empalmada.** Nada más. Este paso no cambia guiones,
ni duración, ni contenido, ni el renderer.

---

## 1. Qué medí y con qué

Todo local, sin API, sin coste. Scripts en `_to_delete/seams/`:

| script | qué hace |
|---|---|
| `seams.py <mp3> <json>` | RMS en los 60 ms previos al `end` de cada segmento y en los 100 ms siguientes |
| `onset.py <mp3>` | perfil en pasos de 10 ms de entradas y salidas |
| `tail.py <mp3> etiqueta@t ...` | los 200 ms alrededor de un instante |
| `corpus.py` | barrido de los 181 videos con sidecar |

Método: decodificar a PCM s16le mono 16 kHz y calcular RMS en numpy. **No usar
`astats` por slice**: mi primer intento lo hizo y devolvió `None` en las 13
filas, lo que imprimió "0 de 13 empalmes" — un cero falso. Ese cero no era un
resultado.

---

## 2. Defecto A — CORRECCIÓN, bloquea

**Los clips bilingües terminan en seco: se cortan en el instante en que la voz
para.**

Medido sobre los 19 vocabularios del corpus, usando aritmética de la línea de
tiempo (`hueco_declarado − PAUSE`, con `repetition_pause() = 0.9` y 0.5 entre
pares):

```
clips "español... english."  (pair)    n=139   cola = 0.000 s en 138  (99.3%)   mediana 0.000 s
clips "english." solo        (repeat)  n=127   cola = 0.000 s en  52  (40.9%)   mediana 0.244 s   max 1.766 s
```

Misma voz, mismo modelo, misma llamada, mismos ajustes. Sólo cambia el texto.
El clip bilingüe **nunca** trae silencio de cola; el clip de una sola frase trae
0.244 s de mediana.

Perfil a 10 ms del final de `pair_0` ("la carta... the menu."), dB, relativo al
`end` del sidecar:

```
        -100  -90  -80  -70  -60  -50  -40  -30  -20  -10   +0  +10  +20
pair_0   -23  -22  -23  -24  -23  -25  -24  -23  -21  -20  -76  -79 -120
pair_3   -47  -48  -49  -50  -49  -48  -51  -45  -53  -66  -92 -120 -120   <- final sano
```

`pair_0` está a **−20 dB — volumen pleno de habla — 10 ms antes de desaparecer**.
No hay caída. Eso es una guillotina, no un final. `pair_3` sí decae.

Barrido del corpus (segmentos cuya cola de 60 ms está por encima de −30 dB y
caen ≥6 dB inmediatamente después), 181 videos, 1 860 segmentos:

```
true_false    44/98   (44.9%)
vocabulary   106/340  (31.2%)
fill_blank    41/189  (21.7%)
quiz          69/590  (11.7%)
educational   58/546  (10.6%)
pronunciation  6/97   ( 6.2%)
```

### Lo que NO pude determinar

**Dónde se corta.** Descarté lo que se puede descartar leyendo el código:

- `_elevenlabs_with_retry` escribe el stream entero, no lo trunca.
- vocabulary **no** llama `trim_clip_silence`; los clips se concatenan enteros.
- el concat re-codifica con `libmp3lame`, no copia frames.
- no hay `silenceremove`, `atrim` ni `loudnorm` en todo `src/`.
- `add_natural_pauses` y `enhance_bilingual_text` no añaden nada al final.

Queda una sola hipótesis viva: **ElevenLabs devuelve el clip ya cortado**. No la
pude probar: intenté regenerar `"la carta... the menu."` desde este entorno y el
proxy de la VM devuelve `httpx.ProxyError: 403 Forbidden` contra
`api.elevenlabs.io`.

**La prueba que falta, y que tú sí puedes correr** (~60 caracteres de API, coste
despreciable):

```python
# src/ en el path, .env cargado
from tts_elevenlabs import generate_segment_audio
from tts_common import get_audio_duration, measure_speech_end
for txt in ["la carta... the menu.", "the menu.", "la carta the menu."]:
    p = f"/tmp/probe_{abs(hash(txt))}.mp3"
    generate_segment_audio(text=txt, output_path=p, segment_type='options')
    print(txt, get_audio_duration(p), measure_speech_end(p))
```

Si el crudo de la API ya viene con cola 0.000 → es ElevenLabs y hay que pedir el
texto con puntuación final distinta o un carácter de guarda. Si el crudo trae
cola y el concatenado no → el corte está en nuestro pipeline y me equivoqué al
descartarlo. **No construyas el arreglo antes de saber cuál de las dos es.**

---

## 3. Defecto B — CALIDAD, avisa

**Cada empalme es voz → cero digital absoluto → voz.**

`generate_silence` usa `anullsrc`, que produce ceros exactos. Verificado a nivel
de muestra: la cuenta atrás del quiz son **72 000 muestras consecutivas
exactamente iguales a cero**.

Una grabación real nunca baja de su suelo de ruido. Medido, el suelo de
ElevenLabs está en −90 dB; nuestros huecos están en −120 dB. El oído no oye el
silencio: oye **desaparecer el suelo de ruido** y volver, 8 a 25 veces por
video. Eso es exactamente el timbre de "cinta empalmada".

Cuánto del audio es cero absoluto:

```
educational / pronunciation      2.3 – 5.1 %
quiz / fill_blank / true_false  29.3 – 38.5 %
vocabulary                      30.3 %
```

Esa tabla es la respuesta a por qué unos tipos suenan bien y otros no. No es el
modelo TTS: comprobé el cruce modelo × tipo y **está confundido** — `turbo_v2_5`
sólo se usa en educational y pronunciation, `v3` sólo en los otros cuatro.
Ningún tipo tiene los dos modelos, así que la diferencia 4 % vs 29 % que sale al
agrupar por modelo **no prueba nada sobre el modelo**. Lo escribo porque yo mismo
casi lo reporto como hallazgo.

### Restricción que cualquier arreglo tiene que respetar

**El arreglo no puede mover la línea de tiempo.** `segment_times` gobierna el
renderer; un `acrossfade` acorta el total y descuadra cada revelado de texto.
Sólo valen arreglos de duración neutra:

- rellenar los huecos con ruido al nivel del suelo del propio clip en vez de
  `anullsrc` (misma duración, mismo `running_time`), o
- un fade de 10–15 ms **dentro** de los límites del clip, al entrar y al salir.

---

## 4. Defecto C — CALIDAD, avisa

**Los clips recortados entran de golpe.**

`TRIM_LEAD_PAD = 0.02` deja 20 ms de arranque. Perfil a 10 ms desde el inicio
del segmento, dB:

```
                  0   10   20   30   40   50   60
option_a       -112  -51  -14  -11  -11  -11  -10     <- recortado
transition     -120  -63  -35  -16  -14  -10   -9     <- recortado
question        -71  -84  -82  -72  -60  -31  -17     <- sin recortar
answer          -86  -81  -72  -74  -72  -78  -81     <- sin recortar
```

`option_a` pasa de silencio digital a volumen pleno en **30 ms**. Ningún
arranque de voz humana hace eso. Los segmentos sin recortar suben en 60–90 ms y
suenan normales.

`add_audio` mide **después** de `_trim`, así que subir `TRIM_LEAD_PAD` es seguro
para la línea de tiempo: la duración se recalcula sobre el clip ya recortado.

---

## 5. Orden de trabajo

1. Correr la prueba de §2 y decir cuál de las dos hipótesis es. **Sólo eso.**
2. Con la respuesta en la mano, arreglar el Defecto A.
3. Defecto B y C después, y sólo si A no los cambia.

No toques guiones, ni duración, ni tipos nuevos, ni el renderer en este paso.

## 6. Lo que NO propongo, y por qué

- **No propongo cambiar de modelo TTS.** El cruce está confundido; no tengo
  evidencia y cambiar de modelo altera la voz entera del canal.
- **No propongo quitar la cuenta atrás silenciosa.** Son 4.5 s por diseño, es una
  decisión de producto tuya, no un defecto.
- **No propongo crossfades.** Rompen `segment_times`.
