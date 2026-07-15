-- Decouple runtime activity logs from database-backed Agent definitions.
ALTER TABLE public.activity_logs
    ADD COLUMN IF NOT EXISTS agent_name character varying(255);

ALTER TABLE public.activity_logs
    ALTER COLUMN agent_id DROP NOT NULL;

ALTER TABLE public.activity_logs
    DROP CONSTRAINT IF EXISTS activity_logs_agent_id_fkey;

ALTER TABLE public.activity_logs
    ADD CONSTRAINT activity_logs_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE SET NULL;
