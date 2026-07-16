"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardTitle, CardDescription } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    // Clicking the emailed reset link redirects here with a recovery token in
    // the URL; supabase-js exchanges it for a session client-side and fires
    // this event once that's done.
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY" || event === "SIGNED_IN") {
        setReady(true);
      }
    });

    // Covers the case where the event already fired before this mounted.
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) setReady(true);
    });

    return () => subscription.unsubscribe();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    const supabase = createClient();
    const { error: updateError } = await supabase.auth.updateUser({
      password,
    });
    setSubmitting(false);

    if (updateError) {
      setError(updateError.message);
      return;
    }

    setDone(true);
  }

  if (done) {
    return (
      <Card>
        <CardTitle>Password updated</CardTitle>
        <CardDescription>
          Your password has been changed. You can now sign in with it.
        </CardDescription>
        <Button
          size="lg"
          className="mt-6 w-full"
          onClick={() => router.replace("/login")}
        >
          Go to sign in
        </Button>
      </Card>
    );
  }

  if (!ready) {
    return (
      <Card>
        <CardTitle>Verifying your reset link</CardTitle>
        <CardDescription>
          This will only take a moment. If nothing happens, your link may
          have expired -- request a new one from the sign in page.
        </CardDescription>
        <div className="mt-6 flex justify-center">
          <Spinner />
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle>Choose a new password</CardTitle>
      <CardDescription>At least 6 characters.</CardDescription>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <Input
          label="New password"
          name="password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 6 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={6}
          required
        />
        <Input
          label="Confirm new password"
          name="confirmPassword"
          type="password"
          autoComplete="new-password"
          placeholder="Re-enter your new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          minLength={6}
          required
        />

        {error ? (
          <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
            {error}
          </p>
        ) : null}

        <Button type="submit" size="lg" disabled={submitting} className="mt-1">
          {submitting ? (
            <>
              <Spinner size={18} className="border-white/40 border-t-white" />
              Updating
            </>
          ) : (
            "Update password"
          )}
        </Button>
      </form>
    </Card>
  );
}
