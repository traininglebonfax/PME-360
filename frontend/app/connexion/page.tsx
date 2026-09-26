"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useState } from "react";

import { BrandName } from "@/components/Brand";
import { Alert, Button, cx, LoadingBlock, TextInput } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { type Brand, DEFAULT_BRAND, useApplyBrand } from "@/lib/brand";
import { homeFor, ME_KEY, type Me, useMe } from "@/lib/session";

type Step = "credentials" | "mfa" | "mfa_setup" | "otp_email" | "otp_code";
type Audience = "gude" | "pme";

export default function LoginPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  // Identité de la page : organisation désignée par ?org=<identifiant>, sinon identité neutre « PME360 ».
  const organization = params.get("org") ?? "";
  const publicBrand = useQuery({
    queryKey: ["public-brand", organization],
    queryFn: () => unwrap(api.GET("/api/v1/public/brand", { params: { query: { org: organization || undefined } } })),
    staleTime: 5 * 60_000,
  });
  const brand: Brand = publicBrand.data ?? DEFAULT_BRAND;
  useApplyBrand(brand);
  const [audience, setAudience] = useState<Audience>("gude");
  const [step, setStep] = useState<Step>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [trusted, setTrusted] = useState(true);
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me && me.portal !== "none") router.replace(homeFor(me));
  }, [me, router]);

  const finish = async () => {
    const fresh = await unwrap(api.GET("/api/v1/me"));
    queryClient.setQueryData<Me | null>(ME_KEY, fresh);
    router.replace(homeFor(fresh));
  };

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const switchAudience = (next: Audience) => {
    setAudience(next);
    setStep(next === "gude" ? "credentials" : "otp_email");
    setError(null);
    setInfo(null);
    setCode("");
  };

  const submitCredentials = (event: FormEvent) => {
    event.preventDefault();
    run(async () => {
      const result = await unwrap(api.POST("/api/v1/auth/login", { body: { email, password } }));
      setPassword("");
      if (result.status === "ok") return finish();
      if (result.status === "mfa_required") return setStep("mfa");
      const secret = await unwrap(api.POST("/api/v1/auth/mfa/setup"));
      setSetup({ secret: secret.secret, qr: await QRCode.toDataURL(secret.otpauth_uri, { margin: 1, width: 180 }) });
      setStep("mfa_setup");
    });
  };

  const submitMfa = (event: FormEvent) => {
    event.preventDefault();
    run(async () => {
      const path = step === "mfa" ? "/api/v1/auth/mfa/verify" : "/api/v1/auth/mfa/confirm";
      await unwrap(api.POST(path, { body: { code } }));
      await finish();
    });
  };

  const requestOtp = (event?: FormEvent) => {
    event?.preventDefault();
    run(async () => {
      await unwrap(api.POST("/api/v1/auth/otp/request", { body: { email } }));
      setInfo("Si cette adresse est associée à un espace PME, un code à 6 chiffres vient de vous être envoyé.");
      setStep("otp_code");
    });
  };

  const submitOtp = (event: FormEvent) => {
    event.preventDefault();
    run(async () => {
      await unwrap(api.POST("/api/v1/auth/otp/verify", { body: { email, code, trusted_device: trusted } }));
      await finish();
    });
  };

  const forgotPassword = () =>
    run(async () => {
      if (!email) {
        setError("Saisissez d'abord votre adresse e-mail.");
        return;
      }
      await unwrap(api.POST("/api/v1/auth/password/reset", { body: { email } }));
      setInfo("Si un compte existe pour cette adresse, un lien de réinitialisation vient d'être envoyé.");
    });

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <BrandName brand={brand} />
        </div>
        <div className="rounded-2xl border border-line bg-white p-6 shadow-sm sm:p-8">
          <div className="mb-6 grid grid-cols-2 gap-1 rounded-lg bg-gray-100 p-1" role="tablist" aria-label="Type d'espace">
            {(["gude", "pme"] as const).map((value) => (
              <button
                key={value}
                role="tab"
                aria-selected={audience === value}
                onClick={() => switchAudience(value)}
                className={cx(
                  "rounded-md px-3 py-2 text-sm font-medium",
                  audience === value ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
                )}
              >
                {value === "gude" ? (brand.short_name ? `Équipe ${brand.short_name}` : "Équipe d'accompagnement") : "Espace PME"}
              </button>
            ))}
          </div>

          {params.get("raison") === "aucune-organisation" && (
            <div className="mb-4">
              <Alert tone="warning" title="Aucun accès actif">
                Votre compte n'est rattaché à aucune organisation. Contactez votre administrateur.
              </Alert>
            </div>
          )}
          {error && (
            <div className="mb-4">
              <Alert>{error}</Alert>
            </div>
          )}
          {info && !error && (
            <div className="mb-4">
              <Alert tone="info">{info}</Alert>
            </div>
          )}

          {step === "credentials" && (
            <form onSubmit={submitCredentials} className="flex flex-col gap-4">
              <TextInput label="Adresse e-mail" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
              <TextInput
                label="Mot de passe"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Button type="submit" loading={busy}>
                Se connecter
              </Button>
              <button type="button" onClick={forgotPassword} className="text-sm text-brand-700 hover:underline">
                Mot de passe oublié ?
              </button>
            </form>
          )}

          {(step === "mfa" || step === "mfa_setup") && (
            <form onSubmit={submitMfa} className="flex flex-col gap-4">
              {step === "mfa_setup" && setup ? (
                <div className="flex flex-col items-center gap-3 text-center text-sm text-muted">
                  <p>
                    La double authentification est obligatoire pour les équipes. Scannez ce QR code avec une application
                    d'authentification (Google Authenticator, Microsoft Authenticator…).
                  </p>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={setup.qr} alt="QR code de configuration de la double authentification" className="h-44 w-44" />
                  <p>
                    Ou saisissez la clé : <code className="break-all rounded bg-gray-100 px-1.5 py-0.5 text-ink">{setup.secret}</code>
                  </p>
                </div>
              ) : (
                <p className="text-sm text-muted">Saisissez le code à 6 chiffres affiché par votre application d'authentification.</p>
              )}
              <TextInput
                label="Code de vérification"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9 ]{6,7}"
                maxLength={7}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                autoFocus
              />
              <Button type="submit" loading={busy}>
                Valider
              </Button>
              <button type="button" onClick={() => switchAudience("gude")} className="text-sm text-muted hover:underline">
                Recommencer
              </button>
            </form>
          )}

          {step === "otp_email" && (
            <form onSubmit={requestOtp} className="flex flex-col gap-4">
              <p className="text-sm text-muted">Pas de mot de passe à retenir : nous vous envoyons un code par e-mail.</p>
              <TextInput label="Adresse e-mail" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              <Button type="submit" loading={busy}>
                Recevoir mon code
              </Button>
            </form>
          )}

          {step === "otp_code" && (
            <form onSubmit={submitOtp} className="flex flex-col gap-4">
              <TextInput
                label="Code reçu par e-mail"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                autoFocus
              />
              <label className="flex items-center gap-2 text-sm text-muted">
                <input type="checkbox" checked={trusted} onChange={(e) => setTrusted(e.target.checked)} className="h-4 w-4 accent-brand-600" />
                Rester connecté 30 jours sur cet appareil
              </label>
              <Button type="submit" loading={busy}>
                Me connecter
              </Button>
              <button type="button" onClick={() => requestOtp()} className="text-sm text-brand-700 hover:underline">
                Renvoyer un code
              </button>
            </form>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-muted">Vos données sont confidentielles et ne sont visibles que par votre conseiller{brand.short_name ? ` ${brand.short_name}` : ""}.</p>
      </div>
    </main>
  );
}
