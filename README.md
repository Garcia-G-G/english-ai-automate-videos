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
│   └── prompts/         # Prompts para Claude
├── src/
│   └── script_generator.py
├── assets/              # Fuentes, imágenes, audio
└── output/              # Videos generados
```

## Pipeline

1. **Script** → Genera prompt con `script_generator.py`, pégalo en Claude
2. **Audio** → (próximo paso) Chatterbox TTS
3. **Video** → (próximo paso) FFmpeg + texto animado
4. **Upload** → (próximo paso) YouTube API, TikTok

## Categorías disponibles

- `phrasal_verbs` - 10 verbos frasales
- `false_friends` - 10 falsos amigos
- `common_mistakes` - 10 errores comunes
