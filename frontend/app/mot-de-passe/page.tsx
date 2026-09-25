"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { BrandName } from "@/components/Brand";
import { Alert, Button, LoadingBlock, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api";

/** Choix du mot de passe (invitation) ou réinitialisation, depuis le lien reçu par e-mail. */
export default function PasswordPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <PasswordForm />
    </Suspense>
  );
}

function PasswordForm() {
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setFieldError(undefined);
    if (password !== confirmation) {
      setFieldError("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setBusy(true);
    try {
      await unwrap(api.POST("/api/v1/auth/password/reset/confirm", { body: { uid, token, new_password: password } }));
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error") setFieldError(err.fieldErrors().new_password);
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <BrandName />
        </div>
        <div className="rounded-2xl border border-line bg-white p-6 shadow-sm sm:p-8">
          <h1 className="mb-4 text-lg font-semibold">Choisir mon mot de passe</h1>
          {!uid || !token ? (
            <Alert>Ce lien est incomplet. Utilisez le lien reçu par e-mail.</Alert>
          ) : done ? (
            <div className="flex flex-col gap-4">
              <Alert tone="success">Votre mot de passe est enregistré.</Alert>
              <Link href="/connexion" className="text-center text-sm font-medium text-brand-700 hover:underline">
                Aller à la connexion
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-4">
              {error && <Alert>{error}</Alert>}
              <TextInput
                label="Nouveau mot de passe"
                type="password"
                autoComplete="new-password"
                hint="12 caractères minimum ; évitez les mots de passe courants."
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                error={fieldError}
                required
              />
              <TextInput
                label="Confirmation"
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                required
              />
              <Button type="submit" loading={busy}>
                Enregistrer
              </Button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
