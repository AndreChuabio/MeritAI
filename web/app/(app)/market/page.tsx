"use client";

import { useState } from "react";
import { OutreachStudio } from "./OutreachStudio";
import { ProfileForm } from "./ProfileForm";
import { StepHeader, type Step } from "./StepHeader";

const STEPS: Step[] = [
  { id: 1, label: "Profile" },
  { id: 2, label: "Generate" },
  { id: 3, label: "Recipient" },
  { id: 4, label: "Send" },
];

export default function MarketPage() {
  // Step 1 (Profile) completes once the profile is saved at least once.
  // Steps 2-4 are reported up from the outreach flow.
  const [profileSaved, setProfileSaved] = useState(false);
  const [outreachStep, setOutreachStep] = useState(1);

  // The further-along of "profile saved" and the live outreach step wins, so
  // the indicator reflects real progress through the flow.
  const current = profileSaved ? Math.max(2, outreachStep) : 1;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <header className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="font-display text-sm font-semibold uppercase tracking-wide text-primary">
            Market
          </span>
          <h1 className="font-display text-3xl font-semibold text-ink">
            Tell your story, then reach out
          </h1>
          <p className="max-w-2xl text-sm text-muted">
            Fill in your profile once, generate a draft, pick who it goes to,
            and open it in your own email to send. Four steps, in order.
          </p>
        </div>
        <StepHeader steps={STEPS} current={current} />
      </header>

      <ProfileForm onSaved={() => setProfileSaved(true)} />
      <OutreachStudio onStepChange={setOutreachStep} />
    </div>
  );
}
