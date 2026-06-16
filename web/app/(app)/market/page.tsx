"use client";

import { OutreachStudio } from "./OutreachStudio";
import { ProfileForm } from "./ProfileForm";

export default function MarketPage() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <header className="flex flex-col gap-2">
        <span className="font-display text-sm font-semibold uppercase tracking-wide text-primary">
          Market
        </span>
        <h1 className="font-display text-3xl font-semibold text-ink">
          Tell your story, then reach out
        </h1>
        <p className="max-w-2xl text-sm text-muted">
          Shape your author profile once, then spin up channel-ready outreach
          drafts that already sound like you.
        </p>
      </header>

      <ProfileForm />
      <OutreachStudio />
    </div>
  );
}
