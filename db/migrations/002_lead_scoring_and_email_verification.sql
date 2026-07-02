-- ============================================================================
-- AI Lead Prospector — Migración 002
-- Motor de scoring ICP (fit + intent) y verificación de email en la tabla `leads`
--
-- Proyecto Supabase: PostgreSQL 17
-- Ejecutar en: Supabase Studio → SQL Editor (o `supabase db push`)
--
-- Contexto (Auditoría de estrategia de prospección):
--   - Antes: `es_calificado` era binario (sí/no) y la calificación dependía de
--     "tener noticias recientes" (intent), descartando buenos prospectos sin prensa.
--   - Ahora: cada lead lleva un score 0–100 compuesto (FIT del ICP + INTENT del
--     trigger) + un tier (A/B/C/D), permitiendo ORDENAR los mejores primero y
--     calificar por encaje (fit-first) aunque no haya trigger reciente.
--   - Además se distingue el ORIGEN del email (verificado vs inferido por patrón)
--     para no contactar a ciegas direcciones que pueden rebotar.
-- ============================================================================

BEGIN;

ALTER TABLE public.leads
  -- Sub-scores (0–100). NULL cuando no aplica (p. ej. role_fit en EMPRESA APTA).
  ADD COLUMN IF NOT EXISTS fit_score        integer,   -- encaje con el ICP (industria, tamaño, geografía, dolor)
  ADD COLUMN IF NOT EXISTS intent_score     integer,   -- fuerza/recencia del trigger de compra (noticias)
  ADD COLUMN IF NOT EXISTS role_fit_score   integer,   -- encaje del cargo del contacto (seniority/decisión)
  -- Score compuesto final (0–100) usado para ranking. Indexado.
  ADD COLUMN IF NOT EXISTS match_score      integer NOT NULL DEFAULT 0,
  -- Tier derivado del match_score: 'A' (>=80), 'B' (60–79), 'C' (40–59), 'D' (<40).
  ADD COLUMN IF NOT EXISTS score_tier       text,
  -- Desglose auditable de cómo se calculó el score (pesos + razones del LLM).
  ADD COLUMN IF NOT EXISTS score_breakdown  jsonb,
  -- Origen del email: 'apollo' | 'hunter' | 'pattern_inferred' | NULL.
  ADD COLUMN IF NOT EXISTS email_source     text,
  -- TRUE solo si el email proviene de una fuente verificada (Apollo/Hunter).
  ADD COLUMN IF NOT EXISTS email_verified   boolean NOT NULL DEFAULT false;

-- Restricción de valores válidos para el tier (idempotente).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'leads_score_tier_check'
  ) THEN
    ALTER TABLE public.leads
      ADD CONSTRAINT leads_score_tier_check
      CHECK (score_tier IS NULL OR score_tier IN ('A', 'B', 'C', 'D'));
  END IF;
END $$;

-- Índice para ordenar "los mejores primero" por usuario/job sin escaneo completo.
CREATE INDEX IF NOT EXISTS idx_leads_user_job_score
  ON public.leads (user_id, job_id, match_score DESC);

COMMIT;

-- ============================================================================
-- ROLLBACK (manual):
--   ALTER TABLE public.leads
--     DROP CONSTRAINT IF EXISTS leads_score_tier_check,
--     DROP COLUMN IF EXISTS fit_score, DROP COLUMN IF EXISTS intent_score,
--     DROP COLUMN IF EXISTS role_fit_score, DROP COLUMN IF EXISTS match_score,
--     DROP COLUMN IF EXISTS score_tier, DROP COLUMN IF EXISTS score_breakdown,
--     DROP COLUMN IF EXISTS email_source, DROP COLUMN IF EXISTS email_verified;
--   DROP INDEX IF EXISTS public.idx_leads_user_job_score;
-- ============================================================================
