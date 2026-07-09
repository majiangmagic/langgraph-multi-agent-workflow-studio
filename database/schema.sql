--
-- PostgreSQL database dump
--

\restrict N6Qk2oWd6mEWfqjjC26o6mkps52iof4HV3EBxfAhpjd6uekAuwDUHXyfaTTMbVV

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: activitytype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.activitytype AS ENUM (
    'TOOL_CALL',
    'AGENT_MESSAGE',
    'PLAN_CREATION',
    'TASK_ASSIGNMENT',
    'TASK_COMPLETION',
    'ERROR',
    'STATUS_CHANGE',
    'CUSTOM'
);


--
-- Name: crewstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.crewstatus AS ENUM (
    'active',
    'inactive',
    'maintenance'
);


--
-- Name: messagerole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.messagerole AS ENUM (
    'USER',
    'ASSISTANT',
    'SYSTEM',
    'AGENT'
);


--
-- Name: messagestatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.messagestatus AS ENUM (
    'PENDING',
    'PROCESSING',
    'COMPLETED',
    'FAILED'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_logs (
    id uuid NOT NULL,
    activity_type public.activitytype NOT NULL,
    description text NOT NULL,
    agent_id uuid NOT NULL,
    conversation_id uuid,
    message_id uuid,
    details json NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: agent_tools; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_tools (
    agent_id uuid NOT NULL,
    mcp_tool_id uuid NOT NULL,
    settings json NOT NULL,
    is_enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: agents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agents (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    system_prompt text NOT NULL,
    model character varying(255) NOT NULL,
    temperature double precision NOT NULL,
    is_supervisor boolean NOT NULL,
    settings json NOT NULL,
    crew_id uuid NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid NOT NULL,
    title character varying(255),
    user_id character varying(255) NOT NULL,
    crew_id uuid NOT NULL,
    meta_data json NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: crew_mcp_servers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crew_mcp_servers (
    crew_id uuid NOT NULL,
    mcp_server_id uuid NOT NULL
);


--
-- Name: crews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crews (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    status public.crewstatus NOT NULL,
    settings json NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: mcp_servers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_servers (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    url character varying(255) NOT NULL,
    settings json NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: mcp_tools; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_tools (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    parameters_schema json NOT NULL,
    mcp_server_id uuid NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id uuid NOT NULL,
    role public.messagerole NOT NULL,
    content text NOT NULL,
    agent_id uuid,
    status public.messagestatus NOT NULL,
    meta_data json NOT NULL,
    conversation_id uuid NOT NULL,
    parent_id uuid,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: activity_logs activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_pkey PRIMARY KEY (id);


--
-- Name: agent_tools agent_tools_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT agent_tools_pkey PRIMARY KEY (agent_id, mcp_tool_id);


--
-- Name: agents agents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT agents_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: crew_mcp_servers crew_mcp_servers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crew_mcp_servers
    ADD CONSTRAINT crew_mcp_servers_pkey PRIMARY KEY (crew_id, mcp_server_id);


--
-- Name: crews crews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crews
    ADD CONSTRAINT crews_pkey PRIMARY KEY (id);


--
-- Name: mcp_servers mcp_servers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_servers
    ADD CONSTRAINT mcp_servers_pkey PRIMARY KEY (id);


--
-- Name: mcp_servers mcp_servers_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_servers
    ADD CONSTRAINT mcp_servers_url_key UNIQUE (url);


--
-- Name: mcp_tools mcp_tools_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_tools
    ADD CONSTRAINT mcp_tools_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: ix_public_activity_logs_activity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_public_activity_logs_activity_type ON public.activity_logs USING btree (activity_type);


--
-- Name: ix_public_activity_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_public_activity_logs_created_at ON public.activity_logs USING btree (created_at);


--
-- Name: ix_public_agents_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_public_agents_name ON public.agents USING btree (name);


--
-- Name: ix_public_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_public_conversations_user_id ON public.conversations USING btree (user_id);


--
-- Name: ix_public_crews_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_public_crews_name ON public.crews USING btree (name);


--
-- Name: ix_public_mcp_servers_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_public_mcp_servers_name ON public.mcp_servers USING btree (name);


--
-- Name: activity_logs activity_logs_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: activity_logs activity_logs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE SET NULL;


--
-- Name: activity_logs activity_logs_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- Name: agent_tools agent_tools_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT agent_tools_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: agent_tools agent_tools_mcp_tool_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT agent_tools_mcp_tool_id_fkey FOREIGN KEY (mcp_tool_id) REFERENCES public.mcp_tools(id) ON DELETE CASCADE;


--
-- Name: agents agents_crew_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT agents_crew_id_fkey FOREIGN KEY (crew_id) REFERENCES public.crews(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_crew_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_crew_id_fkey FOREIGN KEY (crew_id) REFERENCES public.crews(id) ON DELETE CASCADE;


--
-- Name: crew_mcp_servers crew_mcp_servers_crew_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crew_mcp_servers
    ADD CONSTRAINT crew_mcp_servers_crew_id_fkey FOREIGN KEY (crew_id) REFERENCES public.crews(id) ON DELETE CASCADE;


--
-- Name: crew_mcp_servers crew_mcp_servers_mcp_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crew_mcp_servers
    ADD CONSTRAINT crew_mcp_servers_mcp_server_id_fkey FOREIGN KEY (mcp_server_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE;


--
-- Name: mcp_tools mcp_tools_mcp_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_tools
    ADD CONSTRAINT mcp_tools_mcp_server_id_fkey FOREIGN KEY (mcp_server_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE;


--
-- Name: messages messages_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE SET NULL;


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: messages messages_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict N6Qk2oWd6mEWfqjjC26o6mkps52iof4HV3EBxfAhpjd6uekAuwDUHXyfaTTMbVV

