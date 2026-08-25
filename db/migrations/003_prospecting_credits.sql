-- ============================================================================
-- AI Lead Prospector — Migración 003
-- Billetera de créditos de prospección (control de costo Tavily/Apify)
--
-- Proyecto Supabase: PostgreSQL 17
-- Ejecutar en: Supabase Studio → SQL Editor
--
-- Contexto (decisión de negocio 2026-08-25):
--   Tavily ($30/mes, 4.000 créditos) y Apify ($30/mes) son los dos servicios de
--   pago que el Modo Profundo consume por empresa procesada. Sin control, el
--   cliente podría correr el Modo Profundo sin límite y agotar la cuota mensual.
--   Este sistema es FUNCIONAL para contabilizar consumo real y fijar un techo
--   claro — no es un sistema de facturación multi-cliente (single-tenant: todo
--   el consumo cae sobre la cuenta compartida de Élite Logística).
--
--   Unidad: 1 crédito = 1 EMPRESA procesada en Modo Profundo (discovery + news +
--   auditoría; el costo real de Tavily/Apify escala con empresas, no con "jobs").
--   El Modo Rápido no gasta Apify y usa Tavily de forma marginal — no se
--   contabiliza contra el mismo techo por ahora (ver AGENTS.md/SOP 11).
-- ============================================================================

BEGIN;

-- 1. LEDGER DE CONSUMO (append-only, una fila por ejecución de Modo Profundo)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prospecting_credits_usage (
  id                  bigserial PRIMARY KEY,
  user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  job_id              uuid,
  mode                text NOT NULL DEFAULT 'deep' CHECK (mode IN ('deep', 'fast')),
  companies_processed integer NOT NULL DEFAULT 0,
  credits_consumed    integer NOT NULL DEFAULT 0,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_credits_usage_user_month
  ON public.prospecting_credits_usage (user_id, created_at DESC);

-- 2. TECHO MENSUAL POR USUARIO
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prospecting_credit_limits (
  user_id             uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  monthly_credit_limit integer NOT NULL DEFAULT 300,
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- 3. FUNCIÓN: créditos consumidos en el mes calendario actual
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_monthly_credits_used(p_user_id uuid)
RETURNS integer
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(SUM(credits_consumed), 0)::integer
  FROM public.prospecting_credits_usage
  WHERE user_id = p_user_id
    AND created_at >= date_trunc('month', now());
$$;

-- 4. ROW LEVEL SECURITY (mismo patrón que crm_leads/crm_lead_notes)
-- ----------------------------------------------------------------------------
ALTER TABLE public.prospecting_credits_usage  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prospecting_credit_limits  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS credits_usage_select ON public.prospecting_credits_usage;
CREATE POLICY credits_usage_select ON public.prospecting_credits_usage
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS credits_limits_select ON public.prospecting_credit_limits;
CREATE POLICY credits_limits_select ON public.prospecting_credit_limits
  FOR SELECT USING (auth.uid() = user_id);

-- INSERT/UPDATE de estas tablas las hace el backend con SUPABASE_SERVICE_ROLE_KEY
-- (bypassea RLS), igual que el resto de la escritura de `leads`/`jobs_status`.
-- No se agregan políticas de INSERT/UPDATE para el cliente (anon/authenticated).

COMMIT;

-- ============================================================================
-- ROLLBACK (manual):
--   DROP FUNCTION IF EXISTS public.get_monthly_credits_used(uuid);
--   DROP TABLE IF EXISTS public.prospecting_credits_usage;
--   DROP TABLE IF EXISTS public.prospecting_credit_limits;
-- ============================================================================
