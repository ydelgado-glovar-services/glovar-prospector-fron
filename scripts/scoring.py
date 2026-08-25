# scripts/scoring.py
"""
Motor de scoring ICP (Fit + Intent) — AI Lead Prospector.

Fundamento (validado contra el mercado B2B 2026):
  - FIT = qué tan bien encaja la cuenta con el Ideal Customer Profile
    (industria/sub-nicho, tamaño, geografía, alineación con el dolor). Es estable.
  - INTENT = fuerza y recencia de la señal de compra (trigger de noticias). Es volátil.
  - El score final fusiona ambos: "Fit sin señales no avanza; señales sin fit es ruido".
    El FIT domina (califica), el INTENT acelera/prioriza.

Patrón de ruteo implementado en el validador:
  - Alto Fit + Alto Intent  → Tier A (listo para vender, máxima prioridad)
  - Alto Fit + Bajo Intent  → sigue CALIFICADO (nurture) — NO se descarta por falta de prensa
  - Bajo Fit                → descalificado (no encaja con el ICP)

Los sub-scores (0–100) los produce el LLM con una rúbrica; el score compuesto se
calcula de forma DETERMINISTA aquí (más confiable que pedirle el 0–100 final al LLM).
"""

from typing import Optional
import re as _re
import unicodedata as _ud


def _strip_accents(s: str) -> str:
    return "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")


# Acrónimos C-level/VP: se evalúan como PALABRA COMPLETA (token), no substring,
# para no caer en falsos positivos (p. ej. 'cto' dentro de 'direCTOr', 'cio' en 'negoCIO').
_ACRONYM_SCORES = {
    "ceo": 95, "cto": 95, "cio": 95, "cfo": 95, "coo": 95, "cmo": 95,
    "ciso": 95, "cdo": 95, "cao": 95, "cro": 95,
    "vp": 88, "svp": 88, "evp": 88,
}

# Frases/palabras largas: se evalúan por substring (seguro por longitud).
_PHRASE_TIERS = [
    (95, ["chief", "founder", "fundador", "co-founder", "cofundador", "owner",
          "propietario", "presidente", "president", "managing director", "socio director"]),
    (88, ["vicepresident", "vice president", "vicepresidente"]),
    (82, ["director", "directora", "head of", "jefe de", "jefa de",
          "gerente general", "general manager", "country manager"]),
    (68, ["gerente", "manager", "lider", "responsable de", "jefe",
          "principal", "senior manager"]),
    (55, ["coordinador", "coordinadora", "supervisor", "especialista", "specialist", "senior"]),
]

_ROLE_DISQUALIFIERS = [
    "intern", "internship", "becario", "pasante", "practicante", "trainee",
    "assistant", "asistente", "auxiliar", "student", "estudiante", "recepcion",
]


def deterministic_role_fit(title: str, target_roles=None) -> int:
    """role_fit (0-100) REPRODUCIBLE por reglas, robusto al ruido del LLM.
    Acrónimos por palabra completa; frases largas por substring; bono por
    coincidencia (token-a-token) con los cargos objetivo del cliente."""
    if not title:
        return 0
    t = _strip_accents(title).lower()
    tokens = set(_re.findall(r"[a-z0-9]+", t))

    if any(d in t for d in _ROLE_DISQUALIFIERS):
        return 15

    score = 0
    for tok, sc in _ACRONYM_SCORES.items():
        if tok in tokens:
            score = max(score, sc)
    for tier_score, phrases in _PHRASE_TIERS:
        if any(p in t for p in phrases):
            score = max(score, tier_score)

    # Bono por coincidencia con los cargos objetivo (token-a-token, no substring).
    if target_roles:
        for role in target_roles:
            role_tokens = [tok for tok in _re.findall(r"[a-z0-9]+", _strip_accents(str(role)).lower()) if len(tok) >= 3]
            if role_tokens and all(tok in tokens for tok in role_tokens):
                score = max(score, 80)

    return score



# ── Pesos del score compuesto ───────────────────────────────────────────────────
# Con contacto identificado (lead individual):
W_FIT_LEAD = 0.45
W_INTENT_LEAD = 0.30
W_ROLE_LEAD = 0.25

# A nivel cuenta (EMPRESA APTA, sin contacto decisor identificado):
W_FIT_ACCOUNT = 0.60
W_INTENT_ACCOUNT = 0.40

# ── Umbrales ─────────────────────────────────────────────────────────────────────
# Fit mínimo para calificar la cuenta CUANDO hay trigger reciente (intent presente).
FIT_MIN_WITH_INTENT = 45
# Fit mínimo (más exigente) CUANDO no hay trigger reciente, para evitar aprobar
# cuentas solo por conocimiento previo del modelo (anti-alucinación).
FIT_MIN_NO_INTENT = 60

# ── Penalización de TIMING (2026-08-25) ─────────────────────────────────────────
# Decisión de negocio: el valor del producto es llegar en el MOMENTO EXACTO, no solo
# listar empresas del sector. Antes, fit e intent eran ejes independientes (una cuenta
# de alto fit sin trigger igual calificaba con la barra más alta FIT_MIN_NO_INTENT).
# Ahora la falta de señal reciente además RECORTA el fit_score mismo (no solo exige
# una barra más alta), aplicado en validator.py::_run_company_audit ANTES de decidir
# calificación — así el timing pesa en el ranking real, no solo en un umbral binario.
# 0.75 = recorte del 25%: una cuenta de fit excepcional (>=80) todavía puede sobrevivir
# sin trigger (nurture real), pero un fit mediocre (60-75) ya no alcanza el umbral —
# deliberadamente NO es 1.0 (ignoraría el caso "nurture" ya validado) ni <=0.5
# (mataría el nurture por completo); ajustar aquí si el negocio decide otro balance.
TIMING_PENALTY_NO_TRIGGER = 0.75


def _clamp(value, lo: int = 0, hi: int = 100) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(lo, min(hi, v))


def tier_from_score(score: int) -> str:
    """Deriva el tier comercial a partir del score compuesto (0–100)."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def compute_composite(
    fit: int,
    intent: int,
    role_fit: Optional[int] = None,
    reasons: Optional[dict] = None,
) -> dict:
    """Calcula el score compuesto (0–100), su tier y un desglose auditable.

    Si `role_fit` es None se usa la ponderación a nivel cuenta (EMPRESA APTA);
    si viene un valor, se usa la ponderación a nivel lead individual.
    """
    fit = _clamp(fit)
    intent = _clamp(intent)

    if role_fit is None:
        composite = W_FIT_ACCOUNT * fit + W_INTENT_ACCOUNT * intent
        weights = {"fit": W_FIT_ACCOUNT, "intent": W_INTENT_ACCOUNT}
    else:
        role_fit = _clamp(role_fit)
        composite = W_FIT_LEAD * fit + W_INTENT_LEAD * intent + W_ROLE_LEAD * role_fit
        weights = {"fit": W_FIT_LEAD, "intent": W_INTENT_LEAD, "role_fit": W_ROLE_LEAD}

    match_score = _clamp(composite)
    tier = tier_from_score(match_score)

    breakdown = {
        "fit_score": fit,
        "intent_score": intent,
        "role_fit_score": role_fit,
        "weights": weights,
        "match_score": match_score,
        "tier": tier,
    }
    if reasons:
        breakdown["reasons"] = reasons

    return {
        "fit_score": fit,
        "intent_score": intent,
        "role_fit_score": role_fit,
        "match_score": match_score,
        "score_tier": tier,
        "score_breakdown": breakdown,
    }


def account_qualifies(fit: int, has_recent_trigger: bool) -> bool:
    """Decide si la CUENTA califica usando lógica fit-first.

    - Con trigger reciente: basta superar FIT_MIN_WITH_INTENT.
    - Sin trigger reciente: se exige un fit mayor (FIT_MIN_NO_INTENT) para no
      aprobar empresas solo por prior del modelo.
    """
    fit = _clamp(fit)
    threshold = FIT_MIN_WITH_INTENT if has_recent_trigger else FIT_MIN_NO_INTENT
    return fit >= threshold


def disqualified_scores(fit: int, intent: int, reasons: Optional[dict] = None) -> dict:
    """Scoring para filas DESCALIFICADAS: conserva fit/intent por transparencia,
    pero fuerza match_score=0 y tier 'D' para que queden al fondo del ranking
    (no inflar el orden con el intent de una cuenta que no encaja)."""
    fit = _clamp(fit)
    intent = _clamp(intent)
    breakdown = {"fit_score": fit, "intent_score": intent, "match_score": 0, "tier": "D", "disqualified": True}
    if reasons:
        breakdown["reasons"] = reasons
    return {
        "fit_score": fit,
        "intent_score": intent,
        "role_fit_score": None,
        "match_score": 0,
        "score_tier": "D",
        "score_breakdown": breakdown,
    }



# ── Modo Rápido (sin señales de intención/noticias) ─────────────────────────────
# En el Modo Rápido NO se mide intent (no se buscan noticias), por lo que el score
# combina solo FIT firmográfico (la fuente ya filtró industria/geo/tamaño) y el
# encaje del cargo. Evita que un intent=0 castigue injustamente el ranking.
W_FIT_FAST = 0.55
W_ROLE_FAST = 0.45


def compute_fast_match(fit: int, role_fit: int, reasons: Optional[dict] = None) -> dict:
    """Score compuesto para el Modo Rápido: 0.55·fit + 0.45·role_fit (sin intent)."""
    fit = _clamp(fit)
    role_fit = _clamp(role_fit)
    match_score = _clamp(W_FIT_FAST * fit + W_ROLE_FAST * role_fit)
    tier = tier_from_score(match_score)
    breakdown = {
        "fit_score": fit,
        "intent_score": 0,
        "role_fit_score": role_fit,
        "weights": {"fit": W_FIT_FAST, "role_fit": W_ROLE_FAST},
        "match_score": match_score,
        "tier": tier,
        "mode": "fast",
    }
    if reasons:
        breakdown["reasons"] = reasons
    return {
        "fit_score": fit,
        "intent_score": 0,
        "role_fit_score": role_fit,
        "match_score": match_score,
        "score_tier": tier,
        "score_breakdown": breakdown,
    }
