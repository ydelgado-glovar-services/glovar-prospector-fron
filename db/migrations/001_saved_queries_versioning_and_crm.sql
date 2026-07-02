-- ============================================================================
-- AI Lead Prospector — Migración 001
-- Versionado de saved_queries + Mini-CRM (crm_leads, crm_lead_notes)
--
-- Proyecto Supabase: Agent_Scraping_Linkedin (acoefbmluadzscwushcw) — PostgreSQL 17
-- Ejecutar en: Supabase Studio → SQL Editor  (o vía `supabase db push`)
--
-- NOTA DE SEGURIDAD (Auditoría): El backend FastAPI usa SUPABASE_SERVICE_ROLE_KEY,
-- que BYPASSEA RLS. Por eso el aislamiento se refuerza en código con .eq("user_id").
-- Aun así, definimos RLS estricto para proteger cualquier acceso directo con la
-- anon key desde el cliente supabase-js (multi-tenant defense-in-depth).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. VERSIONADO DE saved_queries
--    Permite "sobreescribir como nueva versión" (con etiquetas/fechas) y anclar
--    los resultados de una ejecución (job_id) a una versión concreta de la consulta.
-- ----------------------------------------------------------------------------
ALTER TABLE public.saved_queries
  ADD COLUMN IF NOT EXISTS version          integer      NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS tags             text[]       NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS result_job_id    uuid,
  ADD COLUMN IF NOT EXISTS parent_query_id  uuid REFERENCES public.saved_queries(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS last_run_at      timestamptz,
  ADD COLUMN IF NOT EXISTS updated_at       timestamptz  NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_saved_queries_user        ON public.saved_queries (user_id);
CREATE INDEX IF NOT EXISTS idx_saved_queries_result_job  ON public.saved_queries (result_job_id);

-- Mantener updated_at fresco en cualquier UPDATE (trigger genérico reutilizable).
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_saved_queries_updated_at ON public.saved_queries;
CREATE TRIGGER trg_saved_queries_updated_at
  BEFORE UPDATE ON public.saved_queries
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ----------------------------------------------------------------------------
-- 2. MINI-CRM — Tabla principal de tarjetas (pipeline de leads calificados)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.crm_leads (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL DEFAULT auth.uid(),
  -- Referencia opcional al lead origen (tabla leads.id es bigint).
  lead_id         bigint,
  job_id          uuid,

  -- Snapshot desacoplado de los datos del lead (no se pierde si el origen cambia).
  nombre_lead       text,
  empresa           text,
  cargo             text,
  email             text,
  telefono          text,
  linkedin_url      text,
  trigger_noticia   text,
  mensaje_generado  text,
  url_noticia       text,

  -- Campos propios del CRM.
  stage      text NOT NULL DEFAULT 'nuevo'
             CHECK (stage IN ('nuevo','contactado','en_conversacion','propuesta','ganado','perdido')),
  priority   text NOT NULL DEFAULT 'media'
             CHECK (priority IN ('baja','media','alta')),
  tags       text[] NOT NULL DEFAULT '{}',

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Anti-duplicado: un mismo lead origen no puede entrar dos veces al CRM del usuario.
-- (NULL en lead_id se considera distinto, así que los leads manuales no chocan.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_leads_user_lead
  ON public.crm_leads (user_id, lead_id)
  WHERE lead_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_crm_leads_user_stage ON public.crm_leads (user_id, stage);

DROP TRIGGER IF EXISTS trg_crm_leads_updated_at ON public.crm_leads;
CREATE TRIGGER trg_crm_leads_updated_at
  BEFORE UPDATE ON public.crm_leads
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ----------------------------------------------------------------------------
-- 3. MINI-CRM — Notas internas (timeline por tarjeta)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.crm_lead_notes (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  crm_lead_id  uuid NOT NULL REFERENCES public.crm_leads(id) ON DELETE CASCADE,
  user_id      uuid NOT NULL DEFAULT auth.uid(),
  body         text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crm_notes_lead ON public.crm_lead_notes (crm_lead_id);
CREATE INDEX IF NOT EXISTS idx_crm_notes_user ON public.crm_lead_notes (user_id);

-- ----------------------------------------------------------------------------
-- 4. ROW LEVEL SECURITY (aislamiento multi-tenant)
-- ----------------------------------------------------------------------------
ALTER TABLE public.crm_leads      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_lead_notes ENABLE ROW LEVEL SECURITY;

-- crm_leads: cada usuario solo ve/gestiona sus propias tarjetas.
DROP POLICY IF EXISTS crm_leads_select ON public.crm_leads;
CREATE POLICY crm_leads_select ON public.crm_leads
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS crm_leads_insert ON public.crm_leads;
CREATE POLICY crm_leads_insert ON public.crm_leads
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS crm_leads_update ON public.crm_leads;
CREATE POLICY crm_leads_update ON public.crm_leads
  FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS crm_leads_delete ON public.crm_leads;
CREATE POLICY crm_leads_delete ON public.crm_leads
  FOR DELETE USING (auth.uid() = user_id);

-- crm_lead_notes: mismas reglas de aislamiento.
DROP POLICY IF EXISTS crm_notes_select ON public.crm_lead_notes;
CREATE POLICY crm_notes_select ON public.crm_lead_notes
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS crm_notes_insert ON public.crm_lead_notes;
CREATE POLICY crm_notes_insert ON public.crm_lead_notes
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS crm_notes_delete ON public.crm_lead_notes;
CREATE POLICY crm_notes_delete ON public.crm_lead_notes
  FOR DELETE USING (auth.uid() = user_id);

COMMIT;

-- ============================================================================
-- ROLLBACK (manual, si fuese necesario revertir):
--   DROP TABLE IF EXISTS public.crm_lead_notes;
--   DROP TABLE IF EXISTS public.crm_leads;
--   ALTER TABLE public.saved_queries
--     DROP COLUMN IF EXISTS version, DROP COLUMN IF EXISTS tags,
--     DROP COLUMN IF EXISTS result_job_id, DROP COLUMN IF EXISTS parent_query_id,
--     DROP COLUMN IF EXISTS last_run_at;
-- ============================================================================
