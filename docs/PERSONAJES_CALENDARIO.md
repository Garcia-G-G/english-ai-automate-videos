# Calendario de personajes — Kids & Adults

Dos públicos, dos elencos. Personajes nuevos cada 2 semanas para mantener frescura sin perder consistencia. Todos se crean en Google Flow (proyecto "Momo y Lila EP01" → Caracteres) para reutilizarlos en clips con consistencia garantizada.

## Elenco actual

| Personaje | Público | Rol | Estado |
|-----------|---------|-----|--------|
| Momo (panda rojo) | Kids | Protagonista curioso | ✅ Creado en Flow |
| Lila (luciérnaga) | Kids | Guía sabia | ✅ Creada en Flow |
| Capi (capibara profesor) | Adults | Presentador irónico con café | ✅ Creado en Flow |

## Calendario de lanzamientos (cada 2 semanas)

| Fecha | Kids (+2) | Adults (+1) |
|-------|-----------|-------------|
| 24 jul 2026 | 2 amigos nuevos de Momo (ej. tortuga lenta pero sabia, pájaro apurado) | Compañera de Capi (ej. gata gerente estresada — contraste cómico) |
| 7 ago 2026 | +2 (villano amable / mascota bebé) | +1 (alumno humano torpe) |
| 21 ago 2026 | +2 según qué funcione en analytics | +1 según analytics |

Regla: antes de crear personajes nuevos, revisar qué videos rindieron mejor y diseñar el personaje alrededor de eso.

## Proceso para crear un personaje nuevo (15 min)

1. Flow → proyecto → Caracteres → Nuevo personaje.
2. Prompt con el patrón: `[nombre], a [especie/descripción física detallada], [ropa/accesorio distintivo], [expresión], [escenario típico], Pixar 3D animation style, soft rounded shapes, vibrant saturated colors, shallow depth of field`.
3. Nombrar, llenar "Información del personaje" (personalidad + rol).
4. Generar 3-5 clips de biblioteca (acciones genéricas reutilizables: saludar, pensar, celebrar, señalar, reír) → descargar a `assets/clips/<perfil>/<personaje>/`.

## Bibliotecas de clips

```
assets/clips/
├── kids/
│   ├── momo/        # celebrar, sorprenderse, señalar, reír...
│   ├── lila/        # llegar volando, brillar, guiar...
│   └── <nuevo>/
└── adults/
    └── capi/        # hablar a cámara, sorber café, facepalm, aprobar...
```

Los clips genéricos (sin tema específico) se combinan con voz + texto para cualquier lección → costo casi cero por video.
