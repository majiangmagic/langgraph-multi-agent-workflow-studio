-- Move Workflow selection to Crew and remove the legacy database Agent model.

ALTER TABLE public.crews
    ADD COLUMN IF NOT EXISTS workflow_type character varying(255);

UPDATE public.crews
SET workflow_type = COALESCE(
    NULLIF(settings::jsonb ->> 'workflow_type', ''),
    'supervisor_simple'
)
WHERE workflow_type IS NULL OR workflow_type = '';

UPDATE public.crews
SET settings = (settings::jsonb - 'workflow_type')::json;

ALTER TABLE public.crews
    ALTER COLUMN workflow_type SET DEFAULT 'supervisor_simple',
    ALTER COLUMN workflow_type SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_public_crews_workflow_type
    ON public.crews USING btree (workflow_type);

-- Preserve readable Agent provenance before removing legacy foreign keys.
UPDATE public.activity_logs AS logs
SET agent_name = agents.name
FROM public.agents AS agents
WHERE logs.agent_id = agents.id
  AND (logs.agent_name IS NULL OR logs.agent_name = '');

UPDATE public.messages AS messages
SET meta_data = (
    COALESCE(messages.meta_data::jsonb, '{}'::jsonb)
    || jsonb_build_object('agent_name', agents.name)
)::json
FROM public.agents AS agents
WHERE messages.agent_id = agents.id
  AND NOT (COALESCE(messages.meta_data::jsonb, '{}'::jsonb) ? 'agent_name');

ALTER TABLE public.activity_logs
    DROP CONSTRAINT IF EXISTS activity_logs_agent_id_fkey,
    DROP COLUMN IF EXISTS agent_id;

ALTER TABLE public.messages
    DROP CONSTRAINT IF EXISTS messages_agent_id_fkey,
    DROP COLUMN IF EXISTS agent_id;

DROP TABLE IF EXISTS public.agent_tools;
DROP TABLE IF EXISTS public.agents;
