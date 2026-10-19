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

**Instagram** (Instagram API with Instagram Login)

1. La cuenta de Instagram tiene que ser profesional (Empresa o Creador).
2. En developers.facebook.com: *My Apps → Create app*, caso de uso *Other*, tipo *Business*.
3. En la app: *Add product → Instagram → Set up*. Se añade *API setup with Instagram login*.
4. *App roles → Roles → Instagram Testers → Add*, con nuestra cuenta. Acepta la
   invitación desde Instagram (web: *Configuración → Apps y sitios web → Invitaciones de tester*).
5. En *API setup with Instagram login → Generate access tokens*, añade la cuenta y
   genera el token. Necesita `instagram_business_basic` e `instagram_business_content_publish`.
   Es un token de larga duración (60 días).
6. En `.env`:
   ```
   IG_USER_ID=<id numérico de la cuenta, el que aparece junto al token>
   IG_ACCESS_TOKEN=<token>
   ```

**Facebook** (Reels Publishing API)

1. En *Tools → Graph API Explorer*, elige la app y genera un token de usuario con
   `pages_show_list`, `pages_read_engagement` y `pages_manage_posts`.
2. Cámbialo por uno de larga duración (el secreto de la app está en *App settings → Basic*):
   ```
   curl "https://graph.facebook.com/v26.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=TOKEN_CORTO"
   ```
3. Con ese token, pide los tokens de las páginas. El de la Página no caduca:
   ```
   curl "https://graph.facebook.com/v26.0/me/accounts?access_token=TOKEN_LARGO"
   ```
4. En `.env`: `FB_PAGE_ID=<id>` y `FB_PAGE_TOKEN=<access_token de la página>`.

Comprueba la conexión sin publicar nada: `python3 tools/meta_publish.py check`.

### Renovación del token de Instagram

Antes de cada publicación, si al token le quedan menos de 10 días, se renueva
con `refresh_access_token`. El token nuevo se guarda en
`.tokens/instagram_token.json`: ese directorio está en `.gitignore` y el archivo
tiene permisos 0600. `.env` no se modifica. Si pones un token nuevo en `.env`, el
guardado se descarta y la cadena empieza otra vez desde el nuevo. Si el token
caduca (60 días sin publicar ni renovar), hay que generar otro (paso 5).
Para renovarlo aunque no se publique: `python3 tools/meta_publish.py refresh-token`
(por ejemplo, una vez por semana). `check` y `--dry-run` nunca lo renuevan ni tocan
`.tokens`: solo dicen cuántos días le quedan.

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

