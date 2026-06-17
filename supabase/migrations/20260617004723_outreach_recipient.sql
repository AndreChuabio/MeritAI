-- Add recipient details to outreach_log so "Recent outreach" can show who was
-- reached, and so a draft sent from the Outreach Studio records its recipient.
-- Additive and idempotent.

alter table public.outreach_log
    add column if not exists recipient_name    text not null default '',
    add column if not exists recipient_contact text not null default '';
