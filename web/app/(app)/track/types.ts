/**
 * Page-local types for the Track (O-1A evidence ledger) surface.
 *
 * These mirror the LIVE FastAPI contract, which differs from the shared
 * scaffold types in lib/types.ts. The live API uses snake_case fields:
 *   - evidence_url (not url)
 *   - evidence_date, declared_at, status, metadata
 *   - CriterionGroup carries a human label and a satisfied flag
 * The shared api client casts the JSON, so at runtime these are the real
 * shapes. We adapt at the api.evidence.* boundary in this folder only and
 * never edit lib/*.
 */

/** A single declared evidence item as returned by GET /evidence. */
export interface LiveEvidenceItem {
  id: string;
  criterion: string;
  title: string;
  description: string;
  evidence_url: string;
  evidence_date: string | null;
  declared_at: string;
  status: string;
  metadata: Record<string, unknown>;
}

/** All declared items for one of the eight O-1A criteria. */
export interface LiveCriterionGroup {
  criterion: string;
  label: string;
  satisfied: boolean;
  items: LiveEvidenceItem[];
}

/** The full ledger grouped by criterion with a satisfied count. */
export interface LiveLedger {
  criteria: LiveCriterionGroup[];
  satisfied_count: number;
  total: number;
}

/** Body for POST /evidence and PATCH /evidence/{id}. */
export interface LiveEvidenceInput {
  criterion: string;
  title: string;
  description?: string;
  evidence_url?: string;
  evidence_date?: string | null;
  status?: string;
}

/** Editable fields surfaced in the add/edit form. */
export interface ItemFormValues {
  title: string;
  description: string;
  evidence_url: string;
  evidence_date: string;
}
