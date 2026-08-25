# CLAUDE.md

Lee primero **[AGENTS.md](AGENTS.md)** — es la fuente canónica de contexto de este proyecto (arquitectura, convenciones, riesgos conocidos) y aplica a cualquier agente, incluido Claude Code. Este archivo solo agrega lo específico de Claude Code.

## Notas específicas de Claude Code

- El repositorio git real de este proyecto es `ia_lead_prospector/` (este directorio), no la carpeta padre `ai_lead_prospector/`.
- El frontend Next.js vive anidado en `glovar-prospector-frontend/glovar-prospector-frontend/` — confírmalo con `ls` antes de asumir la ruta al correr `npm`/`npx`.
- Antes de correr `modal deploy`, lee la sección 6 de `AGENTS.md` (checklist de despliegue) — un deploy sin `.env` local completo puede dejar el backend de producción sin secretos.
- Sigue la "Regla de Verdad" de `GEMINI.md`: si cambias un modelo, parámetro o schema en `scripts/` o `app.py`, actualiza el SOP correspondiente en `directivas/` en el mismo cambio.
