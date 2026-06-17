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

/**
 * Plain-language guidance for one O-1A criterion, shown to people who do not
 * know the official USCIS language. `name` is a short friendly label, while the
 * `group.label` from the API carries the long official wording. `examples`
 * gives a couple of concrete things that would count as evidence.
 */
export interface CriterionGuide {
  name: string;
  explanation: string;
  examples: string[];
}

/**
 * Friendly guidance keyed by the eight canonical O-1A criterion keys used by
 * the live API (see paperpilot/outreach/evidence.py USCIS_O1A_CRITERIA).
 */
export const CRITERIA_GUIDE: Record<string, CriterionGuide> = {
  awards: {
    name: "Awards and prizes",
    explanation:
      "Prizes or awards you have won for excellence in your field, recognized at a national or international level.",
    examples: [
      "Best Paper award at a major conference",
      "An industry or competition prize judged against your peers",
    ],
  },
  membership: {
    name: "Selective memberships",
    explanation:
      "Membership in groups that only let you in if outstanding achievement is recognized by experts.",
    examples: [
      "Fellow of a professional society that vets members",
      "An invitation-only association that requires a nomination",
    ],
  },
  media_about: {
    name: "Press about you",
    explanation:
      "Articles or coverage written about you and your work in the press, trade publications, or major media.",
    examples: [
      "A profile or feature about you in a trade publication",
      "A news article covering a project you led",
    ],
  },
  judging: {
    name: "Judging others' work",
    explanation:
      "Times you were asked to evaluate the work of other people in your field.",
    examples: [
      "Reviewing papers for a journal or conference",
      "Serving on an awards panel or grant committee",
    ],
  },
  original_contributions: {
    name: "Original contributions",
    explanation:
      "Original ideas, methods, or products you created that had a major impact on your field.",
    examples: [
      "A technique or system that others now build on",
      "A patent or widely adopted open-source project",
    ],
  },
  scholarly_articles: {
    name: "Published articles",
    explanation:
      "Articles you authored in professional journals, conferences, or major media.",
    examples: [
      "A peer-reviewed paper you wrote or co-wrote",
      "A technical article published in a reputable outlet",
    ],
  },
  critical_role: {
    name: "Critical role",
    explanation:
      "A leading or essential role you played at an organization with a strong reputation.",
    examples: [
      "Founding engineer or tech lead at a well-known company",
      "Heading a key team or initiative at a respected org",
    ],
  },
  high_salary: {
    name: "High salary",
    explanation:
      "Earning a salary or other pay that is high compared with others in your field.",
    examples: [
      "An offer letter or contract showing top-tier compensation",
      "A pay benchmark report placing you above peers",
    ],
  },
};

/**
 * The criterion we steer first-time users toward. Awards are the easiest to
 * understand and document, so they make a friendly starting point.
 */
export const RECOMMENDED_FIRST = "awards";
