"use client";

import { useEffect, useState } from "react";
import type { Profile } from "@/lib/types";
import { api } from "@/lib/api";
import {
  Button,
  Card,
  CardDescription,
  CardTitle,
  Input,
  Spinner,
  Textarea,
} from "@/components/ui";

/**
 * Profile fields as defined by the live backend (ProfileOut / ProfileUpdate).
 * The shared Profile type is loose ([key: string]: unknown), so we narrow to
 * the exact string fields the market profile form edits.
 */
interface MarketProfile {
  name: string;
  title: string;
  about: string;
  voice_tone: string;
  github_url: string;
  linkedin_url: string;
  scholar_url: string;
  site_url: string;
  resume_text: string;
}

const EMPTY_PROFILE: MarketProfile = {
  name: "",
  title: "",
  about: "",
  voice_tone: "",
  github_url: "",
  linkedin_url: "",
  scholar_url: "",
  site_url: "",
  resume_text: "",
};

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

function readString(source: Profile, key: keyof MarketProfile): string {
  const value = source[key];
  return typeof value === "string" ? value : "";
}

/**
 * Accept bare domains in URL fields. A non-empty value without an http(s)
 * scheme gets https:// prepended, so "andrechuabio.github.io" is saved as
 * "https://andrechuabio.github.io" rather than rejected.
 */
function normalizeUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function fromProfile(source: Profile): MarketProfile {
  return {
    name: readString(source, "name"),
    title: readString(source, "title"),
    about: readString(source, "about"),
    voice_tone: readString(source, "voice_tone"),
    github_url: readString(source, "github_url"),
    linkedin_url: readString(source, "linkedin_url"),
    scholar_url: readString(source, "scholar_url"),
    site_url: readString(source, "site_url"),
    resume_text: readString(source, "resume_text"),
  };
}

interface ProfileFormProps {
  /** Called after the profile saves successfully, to advance the flow. */
  onSaved?: () => void;
}

export function ProfileForm({ onSaved }: ProfileFormProps) {
  const [profile, setProfile] = useState<MarketProfile>(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });

  useEffect(() => {
    let active = true;
    api.market
      .getProfile()
      .then((result) => {
        if (!active) return;
        setProfile(fromProfile(result));
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setLoadError(
          err instanceof Error ? err.message : "Could not load your profile.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function update<K extends keyof MarketProfile>(
    key: K,
    value: MarketProfile[K],
  ) {
    setProfile((prev) => ({ ...prev, [key]: value }));
    if (save.kind === "saved" || save.kind === "error") {
      setSave({ kind: "idle" });
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSave({ kind: "saving" });
    try {
      const payload: Profile = {
        ...profile,
        github_url: normalizeUrl(profile.github_url),
        linkedin_url: normalizeUrl(profile.linkedin_url),
        scholar_url: normalizeUrl(profile.scholar_url),
        site_url: normalizeUrl(profile.site_url),
      };
      const result = await api.market.putProfile(payload);
      setProfile(fromProfile(result));
      setSave({ kind: "saved" });
      onSaved?.();
    } catch (err: unknown) {
      setSave({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not save profile.",
      });
    }
  }

  if (loading) {
    return (
      <Card>
        <div className="flex items-center gap-3 text-muted">
          <Spinner size={18} />
          <span className="text-sm">Loading your profile</span>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle>Step 1: Your profile</CardTitle>
          <CardDescription>
            This is what every draft is written from. Name and About are
            required; everything else is optional but makes drafts sharper.
          </CardDescription>
        </div>
      </div>

      {loadError ? (
        <div className="mb-5 rounded-2xl bg-warning/10 px-4 py-3 text-sm text-ink">
          Started with a blank profile. {loadError}
        </div>
      ) : null}

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <Input
            name="name"
            label="Name (required)"
            placeholder="Ada Lovelace"
            value={profile.name}
            onChange={(e) => update("name", e.target.value)}
          />
          <Input
            name="title"
            label="Title (optional)"
            placeholder="Research Engineer"
            value={profile.title}
            onChange={(e) => update("title", e.target.value)}
          />
        </div>

        <Textarea
          name="about"
          label="About (required)"
          placeholder="A few sentences on who you are and what you build."
          value={profile.about}
          onChange={(e) => update("about", e.target.value)}
        />

        <Input
          name="voice_tone"
          label="Voice and tone (optional)"
          placeholder="Warm, direct, a little playful"
          value={profile.voice_tone}
          onChange={(e) => update("voice_tone", e.target.value)}
        />

        <div className="grid gap-5 sm:grid-cols-2">
          <Input
            name="github_url"
            label="GitHub URL (optional)"
            type="text"
            inputMode="url"
            placeholder="https://github.com/you"
            value={profile.github_url}
            onChange={(e) => update("github_url", e.target.value)}
          />
          <Input
            name="linkedin_url"
            label="LinkedIn URL (optional)"
            type="text"
            inputMode="url"
            placeholder="https://linkedin.com/in/you"
            value={profile.linkedin_url}
            onChange={(e) => update("linkedin_url", e.target.value)}
          />
          <Input
            name="scholar_url"
            label="Google Scholar URL (optional)"
            type="text"
            inputMode="url"
            placeholder="https://scholar.google.com/..."
            value={profile.scholar_url}
            onChange={(e) => update("scholar_url", e.target.value)}
          />
          <Input
            name="site_url"
            label="Personal site URL (optional)"
            type="text"
            inputMode="url"
            placeholder="https://you.dev"
            value={profile.site_url}
            onChange={(e) => update("site_url", e.target.value)}
          />
        </div>

        <Textarea
          name="resume_text"
          label="Resume text (optional)"
          placeholder="Paste your resume or a longer bio for richer drafts."
          className="min-h-40"
          value={profile.resume_text}
          onChange={(e) => update("resume_text", e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" disabled={save.kind === "saving"}>
            {save.kind === "saving" ? (
              <>
                <Spinner size={16} className="border-white/40 border-t-white" />
                Saving
              </>
            ) : (
              "Save profile"
            )}
          </Button>
          {save.kind === "saved" ? (
            <span className="text-sm font-medium text-success">
              Saved. Your drafts will use the latest profile.
            </span>
          ) : null}
          {save.kind === "error" ? (
            <span className="text-sm font-medium text-danger">
              {save.message}
            </span>
          ) : null}
        </div>
      </form>
    </Card>
  );
}
