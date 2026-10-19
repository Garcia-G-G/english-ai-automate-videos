# 🎬 English AI Video Generator

Videos de inglés para hispanohablantes.

## Uso rápido

```bash
# Ver categorías disponibles
python src/script_generator.py --list

# Generar prompt para una categoría
python src/script_generator.py -c phrasal_verbs
python src/script_generator.py -c false_friends
python src/script_generator.py -c common_mistakes

# Aleatorio
python src/script_generator.py
```

## Estructura

```
├── content/
│   ├── topics/          # Base de datos de temas (JSON)
│   └── prompts/         # Prompts para el generador de guiones
├── src/
│   └── script_generator.py
├── assets/              # Fuentes, imágenes, audio
└── output/              # Videos generados
```

## Pipeline

1. **Script** → Genera prompt con `script_generator.py`, pégalo en tu asistente de IA
2. **Audio** → (próximo paso) Chatterbox TTS
3. **Video** → (próximo paso) FFmpeg + texto animado
4. **Upload** → YouTube, TikTok, e Instagram/Facebook Reels (ver abajo)

## Categorías disponibles

- `phrasal_verbs` - 10 verbos frasales
- `false_friends` - 10 falsos amigos
- `common_mistakes` - 10 errores comunes

## Meta Reels (Instagram y Facebook)

`src/publishers/` publica los vídeos aprobados como Reels en nuestra cuenta de
Instagram y en nuestra Página de Facebook, con las APIs oficiales de Meta
(Graph API v26.0). La app de Meta se queda en modo desarrollo: solo publica en
cuentas que tienen un rol en la app, así que no hace falta App Review.

### Configuración (una sola vez)

Instagram y Facebook usan **el mismo token: el de la Página** (Instagram API con
Facebook Login). No hay que alojar el vídeo en ningún sitio y el token no caduca.

1. La cuenta de Instagram tiene que ser profesional (Empresa o Creador) y estar
   **vinculada a la Página**: Meta Business Suite → *Configuración → Cuentas de Instagram*.
2. En developers.facebook.com, abre la app (o créala: *My Apps → Create app*, tipo *Business*).
3. *Tools → Graph API Explorer*: elige la app y genera un token de usuario con estos 5 permisos:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`.
4. Cámbialo por uno de larga duración (el secreto de la app está en *App settings → Basic*):
   ```
   curl "https://graph.facebook.com/v26.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=TOKEN_CORTO"
   ```
5. Con ese token, pide los de tus páginas. El de la Página sacado así no caduca:
   ```
   curl "https://graph.facebook.com/v26.0/me/accounts?access_token=TOKEN_LARGO"
   ```
6. En `.env`: `FB_PAGE_ID=<id de la Página>` y `FB_PAGE_TOKEN=<access_token de la Página>`.
   `IG_USER_ID` es opcional: el id de Instagram se lee de la Página y se guarda en
   `.tokens/meta_ids.json` (0600).
7. Ejecuta `python3 tools/meta_publish.py setup-check` (o `make meta-check`). Dice la
   Página, la cuenta de Instagram vinculada, el tipo y la caducidad del token, los
   permisos que faltan y cómo arreglar cada cosa. Sale con código 0 solo si todo está.
   El panel tiene el mismo informe en la tarjeta de la cola de Instagram/Facebook.

`python3 tools/meta_publish.py check` y `--dry-run` solo hacen lecturas: no
publican ni escriben nada. `refresh-token` ya no renueva nada; solo muestra el tipo
y la caducidad del token de la Página.

Si en el panel una plataforma falla por la configuración (permisos, token o Instagram
sin vincular), queda en «configuración pendiente» para el resto del lote y las demás
siguen.

### Cola y horarios

Solo entran vídeos aprobados (`output/approved/`). Para encolarlos, usa el botón 📅
del panel *Upload*, `python3 tools/meta_publish.py enqueue --approved`, o pon
`meta_publish.auto_enqueue_on_approve: true` en `config.yaml` para que se encolen
al aprobarlos. En cada franja de `meta_publish.slots` (por defecto 10:00 y 19:00)
sale un vídeo hacia todas las plataformas que le falten.

```
python3 tools/meta_publish.py list               # estado: queued / published / failed / holding + enlace
python3 tools/meta_publish.py tick --dry-run     # qué se publicaría ahora, sin publicar
python3 tools/meta_publish.py now --dry-run      # igual, sin esperar a la franja
python3 tools/meta_publish.py now [ARTEFACTO]    # publicar ya (también reintenta uno fallido)
python3 tools/meta_publish.py loop               # tick cada 5 min, en una terminal abierta
```

O desde cron (en macOS, cron necesita *Acceso total al disco* para leer `~/Downloads`):

```
*/5 * * * * cd /path/to/english-ai-videos && /usr/bin/python3 tools/meta_publish.py tick >> logs/meta_publish.log 2>&1
```

Cambia `/path/to/english-ai-videos` por la carpeta real del proyecto en tu máquina.

Antes de subir nada se comprueba el archivo contra la especificación de Reels:
MP4/MOV, H.264/HEVC, 9:16, al menos 540 px de ancho, 23–60 fps (Facebook 24–60),
audio AAC a 48 kHz como máximo, y entre 3 s y 15 min en Instagram o entre 3 y 90 s en
Facebook. Si algo no cumple, falla antes de enviar nada y dice qué.

Límites: antes de publicar se consulta `content_publishing_limit` de Instagram.
En Facebook, el límite de 30 Reels cada 24 h se cuenta en `output/published/attempts.jsonl`.

Para no publicar dos veces, se usan el mismo registro de intentos y el mismo
ledger que las demás subidas (`output/published/`). Si se pierde la respuesta de
publicación, se consulta el estado del contenedor o del Reel. La llamada `finish`
de Facebook no se repite nunca sin revisar primero el estado. Lo que no se puede
confirmar se queda en `holding` y no se reintenta solo.

