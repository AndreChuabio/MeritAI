import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardTitle, CardDescription } from "@/components/ui/Card";

const FEATURES: ReadonlyArray<{
  tag: string;
  tone: "primary" | "pink" | "lime";
  title: string;
  description: string;
}> = [
  {
    tag: "Productize",
    tone: "primary",
    title: "Turn a repo into a paper",
    description:
      "Ingest your research code, match it to the right venues, and draft a full paper section by section.",
  },
  {
    tag: "Market",
    tone: "pink",
    title: "Draft your outreach",
    description:
      "Generate sharp, personalized outreach messages so your work lands in front of the people who matter.",
  },
  {
    tag: "Track",
    tone: "lime",
    title: "Track your O-1A progress",
    description:
      "Build an evidence ledger across all eight O-1A criteria and export a dossier when you are ready.",
  },
];

export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    redirect("/productize");
  }

  return (
    <div className="flex flex-1 flex-col px-5 py-16">
      <section className="mx-auto w-full max-w-3xl text-center">
        <div className="mb-6 flex justify-center">
          <Badge tone="lime">Research to results, on autopilot</Badge>
        </div>
        <h1 className="font-display text-5xl font-bold leading-tight tracking-tight text-ink sm:text-6xl">
          Turn your work into{" "}
          <span className="text-primary">recognition</span>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg text-muted">
          Merit ingests your research, matches it to venues, drafts the
          paper, writes your outreach, and tracks your O-1A visa progress.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/signup">
            <Button size="lg">Create account</Button>
          </Link>
          <Link href="/login">
            <Button variant="secondary" size="lg">
              Sign in
            </Button>
          </Link>
        </div>
      </section>

      <section className="mx-auto mt-16 grid w-full max-w-5xl gap-5 sm:grid-cols-3">
        {FEATURES.map((feature) => (
          <Card key={feature.tag} interactive>
            <Badge tone={feature.tone}>{feature.tag}</Badge>
            <CardTitle className="mt-4">{feature.title}</CardTitle>
            <CardDescription>{feature.description}</CardDescription>
          </Card>
        ))}
      </section>
    </div>
  );
}
