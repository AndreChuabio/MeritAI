"""FastAPI backend for PaperPilot.

Wraps the existing paperpilot/ pipeline as an HTTP API consumed by the
Next.js frontend. Authentication is delegated to Supabase Auth; the data
layer is Supabase Postgres + pgvector via paperpilot.supabase_client.
"""
