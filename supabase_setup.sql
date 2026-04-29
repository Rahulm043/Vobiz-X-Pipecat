-- ==========================================
-- SUPABASE SETUP SCRIPT FOR VOBIZ-X-PIPECAT
-- ==========================================

-- 1. Create Tables
-- ------------------------------------------

-- Table for Call Records
CREATE TABLE IF NOT EXISTS public.calls (
    call_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID,
    phone_number TEXT NOT NULL,
    recipient_name TEXT,
    recipient_detail TEXT,
    call_type TEXT DEFAULT 'sip',
    status TEXT DEFAULT 'queued',
    direction TEXT DEFAULT 'outbound',
    created_at TIMESTAMPTZ DEFAULT now(),
    ringing_at TIMESTAMPTZ,
    connected_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds FLOAT DEFAULT 0,
    duration_minutes INTEGER DEFAULT 0,
    vobiz_call_uuid TEXT,
    recording_files JSONB DEFAULT '{"stereo": null, "user": null, "bot": null, "vobiz_mp3": null}'::jsonb,
    transcript JSONB DEFAULT '[]'::jsonb,
    summary TEXT,
    end_reason TEXT,
    transfer_requested BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Table for Campaigns
CREATE TABLE IF NOT EXISTS public.campaigns (
    campaign_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT DEFAULT 'created',
    mode TEXT DEFAULT 'sequential',
    concurrent_limit INTEGER DEFAULT 1,
    call_gap_seconds INTEGER DEFAULT 30,
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    recipients JSONB DEFAULT '[]'::jsonb,
    stats JSONB DEFAULT '{"total": 0, "completed": 0, "failed": 0, "rejected": 0, "active": 0, "queued": 0}'::jsonb
);

-- 2. Indexes for Performance
-- ------------------------------------------
CREATE INDEX IF NOT EXISTS idx_calls_campaign_id ON public.calls(campaign_id);
CREATE INDEX IF NOT EXISTS idx_calls_vobiz_uuid ON public.calls(vobiz_call_uuid);
CREATE INDEX IF NOT EXISTS idx_calls_created_at ON public.calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON public.campaigns(created_at DESC);

-- 3. Storage Setup
-- ------------------------------------------
-- Create bucket for recordings (Run this in the Supabase UI or use SQL if supported)
-- INSERT INTO storage.buckets (id, name, public) VALUES ('recordings', 'recordings', false);

-- Enable Row Level Security (Optional, but recommended)
-- ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.campaigns ENABLE ROW LEVEL SECURITY;

-- Simple policy: authenticated users can do everything
-- CREATE POLICY "Allow all actions for authenticated users" ON public.calls FOR ALL TO authenticated USING (true);
-- CREATE POLICY "Allow all actions for authenticated users" ON public.campaigns FOR ALL TO authenticated USING (true);
