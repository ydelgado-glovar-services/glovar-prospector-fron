# scripts/runtime_paths.py
"""
Aislamiento de artefactos temporales por job_id.

PROBLEMA QUE RESUELVE (root cause de la contaminación entre corridas):
El pipeline escribía/leía archivos GLOBALES no namespaceados:
  - `.tmp/active_runtime_context.json`  (uno solo para TODO el sistema)
  - `.tmp/news_{empresa}.json` / `.tmp/leads_{empresa}.json`  (solo por empresa)
Cuando dos jobs corrían concurrentes o casi seguidos (mismo o distinto usuario),
el segundo pisaba el contexto del primero y los hilos del validador/scraper leían
el contexto equivocado → una búsqueda de "constructoras" terminaba auditando CROs.

SOLUCIÓN: todo artefacto intermedio vive bajo `.tmp/job_{job_id}/`, de modo que
cada corrida está completamente aislada de las demás.
"""

import os
import re


def _safe(name: str) -> str:
    """Sanitiza el nombre de empresa para usarlo como nombre de archivo seguro
    (los nombres pueden traer '/', acentos, comillas, etc. desde Tavily/RAG)."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    s = s.strip("._-")
    return s[:80] or "company"


def job_dir(job_id: str) -> str:
    """Directorio aislado de la corrida. Lo crea si no existe."""
    safe_job = re.sub(r"[^A-Za-z0-9_-]+", "_", (job_id or "default").strip()) or "default"
    d = os.path.join(".tmp", f"job_{safe_job}")
    os.makedirs(d, exist_ok=True)
    return d


def context_path(job_id: str) -> str:
    """Ruta del contexto de runtime (manifiesto cognitivo de la Fase 0) por job."""
    return os.path.join(job_dir(job_id), "active_runtime_context.json")


def news_path(job_id: str, company: str) -> str:
    """Ruta del staging de noticias de una empresa dentro de la corrida."""
    return os.path.join(job_dir(job_id), f"news_{_safe(company)}.json")


def leads_path(job_id: str, company: str) -> str:
    """Ruta del staging de leads de una empresa dentro de la corrida."""
    return os.path.join(job_dir(job_id), f"leads_{_safe(company)}.json")
