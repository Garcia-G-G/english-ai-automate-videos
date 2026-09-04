# Todo lo que publica el dashboard sale en privado

**Encontrado verificando E1.** `HEAD 6902167`. Urgente.

---

## 1 · Hoy se publicaron CINCO videos, no uno

El informe describe una publicación (`break_the_ice`, P1). El ledger dice otra cosa:

| hora | artefacto | id |
|---|---|---|
| 16:37:47 | `doggy_bag_to-go_box_20260821_152336` | `fuVi_ZwUlzo` |
| 16:37:56 | `used_to_vs_would_20260821_152332` | `TifTARm3LMs` |
| 16:38:04 | `breathe_20260821_141707` | `zegCeCKWm2g` |
| 16:38:09 | `on_the_house_20260821_141307` | `cWBqMwmRT3w` |
| 16:51:47 | `break_the_ice` | `XL81nQiBfwE` ← el único reportado |

Cuatro a las 16:37-16:38, separados por ~8 segundos: eso es una acción en lote. El de P1 llegó 13 minutos después.

**No sé quién los subió** — pudo ser el operador probando la interfaz, o pudo ser una subida en lote que no se reportó. No lo afirmo. Pero publicar es irreversible y es la superficie de más riesgo del proyecto: **el informe dice uno y el ledger dice cinco, y eso hay que resolverlo antes de seguir.**

---

## 2 · Los cinco están en privado. Y todo lo que ha subido el dashboard, siempre

`src/uploader.py:73`:

```python
@dataclass
class VideoMetadata:
    privacy: str = "private"   # private | public | unlisted
```

`src/uploader.py:693`, dentro del subidor de YouTube:

```python
meta = VideoMetadata(title, description, hashtags or [])   # <- tres posicionales
```

`privacy` se queda con el default. `uploader.py:704` → `privacy_status = "private"` → `body["status"]["privacyStatus"] = "private"`.

No hay variable de entorno. No hay clave en `config.yaml`. No hay nada en `.env.example`. `resolve_upload_metadata` no devuelve `privacy`.

### Y ahora la parte que duele

`main.py:362`:

```python
privacy="public",
```

**El camino `--batch` publica en público. El del dashboard no pasa nada y sale privado.**

> ### Sexta instancia de la divergencia `main.py` / `admin.py`
>
> 1. los dos pipelines de TTS · Paso 0
> 2. la tercera ruta de subida · 5a Prompt 1
> 3. `finalize_video` con 0 llamadores — gate y outro · 5a Prompt 4
> 4. `_static_frame` cacheando sin mirar el preset · `4b3bd19`
> 5. el fondo generado por video · F2
> 6. **la privacidad de la publicación** ← aquí
>
> Y esta es la peor de las seis. Las otras costaban calidad. Esta significa que **todo lo que este proyecto ha publicado por el dashboard ha salido a una audiencia de cero**.

---

## Lo que esto explica

Llevamos toda la sesión arreglando la cadena para que un video llegue a publicarse con el CTA de Learning Routes. Los seis del lote eran los primeros. **Están en el canal y no los ve nadie.** Cero vistas por construcción, no por distribución.

Y encaja con lo que el canal venía diciendo: los videos con vistas reales (225, 230) son los que se subieron a mano antes de que existiera esta ruta.

## La decisión, que no es mía

El arreglo es una línea. Pero `private` puede no ser un descuido:

- **TikTok lo exige.** Un cliente sin auditar solo puede publicar en `SELF_ONLY` (`uploader.py:460`). Ahí `private` es correcto y obligatorio.
- **YouTube no.** Ahí `private` anula el propósito entero.

Así que no es "quitar el default": es **que la privacidad se decida por plataforma y sea visible en la pantalla antes de pulsar**, no un default de dataclass que nadie ve.

Y los cinco de hoy hay que pasarlos a público a mano en YouTube, o volver a decidir uno por uno.

---

## Y una tercera, del propio informe

> *"the upload-target checkboxes default to checked for every connected platform — `reconcile_platform_target` sets TikTok on as soon as the page renders. During P1 I had to explicitly uncheck TikTok twice."*

Bien reportado. Pero **no es cosa de E4.** Una casilla que se arma sola al renderizar, en una página cuyo botón publica de forma irreversible, es un seguro quitado — la misma familia que el veredicto del gate sin llegar a Review: la pantalla presenta un estado que el operador no eligió.

Con el hallazgo de privacidad al lado, el riesgo se compone: una pulsación distraída publica en una plataforma no elegida, con una privacidad que nadie vio.

**Va ahora, con el arreglo de privacidad. Es un default, no un rediseño.**
