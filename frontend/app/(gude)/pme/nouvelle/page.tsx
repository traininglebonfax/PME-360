"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Alert, Badge, Button, Card, cx, PageHeader, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { PERSON_ROLE_LABELS, SIZE_LABELS } from "@/lib/labels";
import { toOptions, useReference } from "@/lib/references";
import { hasPermission, useMe } from "@/lib/session";

type Duplicate = Schemas["Duplicate"];

const STEPS = ["Identité légale", "Activité et localisation", "Dirigeant et suivi"] as const;

const EMPTY = {
  legal_name: "",
  trade_name: "",
  legal_form: "",
  rccm_number: "",
  ncc: "",
  cnps_employer_number: "",
  creation_date: "",
  sector: "",
  region: "",
  commune: "",
  address: "",
  phone: "",
  email: "",
  website: "",
  headcount: "",
  size_category: "NON_DETERMINEE",
  person_name: "",
  person_role: "GERANT",
  person_phone: "",
  person_email: "",
  advisor_id: "",
  cohort_id: "",
  start_onboarding: true,
};

type Form = typeof EMPTY;

/** Assistant de création en 3 étapes avec détection des doublons (Document 1, § 4, étape 1). */
export default function NewPmePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const legalForms = useReference("legal-forms");
  const sectors = useReference("sectors");
  const regions = useReference("regions");
  const advisors = useQuery({ queryKey: ["advisors"], queryFn: () => unwrap(api.GET("/api/v1/users/advisors")) });
  const programmes = useQuery({ queryKey: ["programmes"], queryFn: () => unwrap(api.GET("/api/v1/programmes")) });
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [duplicates, setDuplicates] = useState<Duplicate[]>([]);
  const [blocking, setBlocking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof Form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = event.target as HTMLInputElement;
    setForm((current) => ({ ...current, [key]: target.type === "checkbox" ? target.checked : target.value }));
    setErrors((current) => ({ ...current, [key]: "" }));
  };

  const cohorts = (programmes.data ?? []).flatMap((programme) =>
    programme.cohorts.map((cohort) => ({ value: cohort.id, label: `${programme.name} — ${cohort.name}` })),
  );
  const canAssign = hasPermission(me, "pme.assign");

  const checkDuplicates = async () => {
    const found = await unwrap(
      api.GET("/api/v1/pmes/duplicates", {
        params: { query: { legal_name: form.legal_name, rccm_number: form.rccm_number, ncc: form.ncc } },
      }),
    );
    setDuplicates(found);
    setBlocking(found.some((d) => d.reasons.includes("rccm") || d.reasons.includes("ncc")));
    return found;
  };

  const next = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (step === 0) {
      if (form.legal_name.trim().length < 2) {
        setErrors({ legal_name: "La raison sociale est obligatoire." });
        return;
      }
      setBusy(true);
      try {
        const found = await checkDuplicates();
        if (found.some((d) => d.reasons.includes("rccm") || d.reasons.includes("ncc"))) return;
      } catch (err) {
        setError(errorMessage(err));
        return;
      } finally {
        setBusy(false);
      }
    }
    if (step < STEPS.length - 1) setStep(step + 1);
    else await submit();
  };

  const submit = async () => {
    setBusy(true);
    try {
      const body: Schemas["PmeCreateRequest"] = {
        legal_name: form.legal_name,
        trade_name: form.trade_name,
        legal_form: form.legal_form || null,
        rccm_number: form.rccm_number,
        ncc: form.ncc,
        cnps_employer_number: form.cnps_employer_number,
        creation_date: form.creation_date || null,
        sector: form.sector || null,
        region: form.region || null,
        commune: form.commune,
        address: form.address,
        phone: form.phone,
        email: form.email,
        website: form.website,
        headcount: form.headcount === "" ? null : Number(form.headcount),
        size_category: form.size_category as Schemas["SizeCategoryEnum"],
        advisor_id: form.advisor_id || null,
        cohort_id: form.cohort_id || null,
        start_onboarding: form.start_onboarding,
        confirm_duplicates: duplicates.length > 0,
        ...(form.person_name
          ? {
              primary_person: {
                full_name: form.person_name,
                role: form.person_role as Schemas["RoleEnum"],
                phone: form.person_phone,
                email: form.person_email,
              },
            }
          : {}),
      };
      const pme = await unwrap(api.POST("/api/v1/pmes", { body }));
      await queryClient.invalidateQueries({ queryKey: ["pmes"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      router.push(`/pme/${pme.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error") {
        const fieldErrors = err.fieldErrors();
        setErrors(fieldErrors);
        const firstStep = Object.keys(fieldErrors).some((k) => ["legal_name", "rccm_number", "ncc", "creation_date", "legal_form"].includes(k))
          ? 0
          : Object.keys(fieldErrors).some((k) => !k.startsWith("primary_person") && k !== "advisor_id" && k !== "cohort_id")
            ? 1
            : 2;
        setStep(firstStep);
        setError("Certaines informations sont à corriger.");
      } else if (err instanceof ApiError && (err.code === "possible_duplicates" || err.code === "duplicate_identifier")) {
        setDuplicates((err.problem.duplicates as Duplicate[]) ?? []);
        setBlocking(err.code === "duplicate_identifier");
        setStep(0);
      } else {
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Nouvelle PME" subtitle="Création de la fiche d'identité de l'entreprise" />
      <ol className="mb-6 grid gap-2 sm:grid-cols-3" aria-label="Étapes">
        {STEPS.map((label, index) => (
          <li
            key={label}
            aria-current={index === step ? "step" : undefined}
            className={cx(
              "rounded-lg border px-4 py-3 text-sm",
              index === step ? "border-brand-600 bg-brand-50 font-medium text-brand-800" : index < step ? "border-line bg-white text-ink" : "border-line bg-white text-muted",
            )}
          >
            <span className="mr-2 tabular-nums">{index + 1}.</span>
            {label}
          </li>
        ))}
      </ol>

      <form onSubmit={next} className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          {error && (
            <div className="mb-4">
              <Alert>{error}</Alert>
            </div>
          )}
          {step === 0 && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <TextInput label="Raison sociale" value={form.legal_name} onChange={set("legal_name")} error={errors.legal_name} required autoFocus />
              </div>
              <TextInput label="Sigle ou nom commercial" value={form.trade_name} onChange={set("trade_name")} error={errors.trade_name} />
              <SelectInput label="Forme juridique" value={form.legal_form} onChange={set("legal_form")} options={toOptions(legalForms.data)} error={errors.legal_form} />
              <TextInput label="N° RCCM" placeholder="CI-ABJ-2020-B-12345" value={form.rccm_number} onChange={set("rccm_number")} error={errors.rccm_number} />
              <TextInput label="N° compte contribuable (NCC)" value={form.ncc} onChange={set("ncc")} error={errors.ncc} />
              <TextInput label="N° employeur CNPS" value={form.cnps_employer_number} onChange={set("cnps_employer_number")} error={errors.cnps_employer_number} />
              <TextInput label="Date de création" type="date" value={form.creation_date} onChange={set("creation_date")} error={errors.creation_date} />
            </div>
          )}
          {step === 1 && (
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectInput label="Secteur d'activité" value={form.sector} onChange={set("sector")} options={toOptions(sectors.data)} error={errors.sector} />
              <TextInput label="Effectif déclaré" type="number" min={0} value={form.headcount} onChange={set("headcount")} error={errors.headcount} />
              <SelectInput
                label="Taille (déclarée)"
                value={form.size_category}
                onChange={set("size_category")}
                placeholder="Non déterminée"
                options={Object.entries(SIZE_LABELS)
                  .filter(([value]) => value !== "NON_DETERMINEE")
                  .map(([value, label]) => ({ value, label }))}
                hint="Calculée automatiquement une fois les seuils réglementaires vérifiés."
              />
              <SelectInput label="Région ou district" value={form.region} onChange={set("region")} options={toOptions(regions.data)} error={errors.region} />
              <TextInput label="Commune" value={form.commune} onChange={set("commune")} error={errors.commune} />
              <TextInput label="Adresse" value={form.address} onChange={set("address")} error={errors.address} />
              <TextInput label="Téléphone" type="tel" value={form.phone} onChange={set("phone")} error={errors.phone} />
              <TextInput label="E-mail de l'entreprise" type="email" value={form.email} onChange={set("email")} error={errors.email} />
              <TextInput label="Site web" type="url" placeholder="https://" value={form.website} onChange={set("website")} error={errors.website} />
            </div>
          )}
          {step === 2 && (
            <div className="grid gap-4 sm:grid-cols-2">
              <p className="text-sm font-medium text-ink sm:col-span-2">Dirigeant principal (contact)</p>
              <TextInput label="Nom complet" value={form.person_name} onChange={set("person_name")} error={errors["primary_person.full_name"]} />
              <SelectInput
                label="Fonction"
                value={form.person_role}
                onChange={set("person_role")}
                options={Object.entries(PERSON_ROLE_LABELS).map(([value, label]) => ({ value, label }))}
              />
              <TextInput label="Téléphone" type="tel" value={form.person_phone} onChange={set("person_phone")} />
              <TextInput label="E-mail" type="email" value={form.person_email} onChange={set("person_email")} error={errors["primary_person.email"]} />
              <p className="mt-2 text-sm font-medium text-ink sm:col-span-2">Suivi</p>
              {canAssign ? (
                <SelectInput
                  label="Conseiller principal"
                  placeholder="À assigner plus tard"
                  value={form.advisor_id}
                  onChange={set("advisor_id")}
                  options={(advisors.data ?? []).map((user) => ({ value: user.id, label: user.full_name }))}
                  error={errors.advisor_id}
                />
              ) : (
                <p className="text-sm text-muted">Vous serez le conseiller principal de cette PME.</p>
              )}
              <SelectInput label="Cohorte" placeholder="Aucune" value={form.cohort_id} onChange={set("cohort_id")} options={cohorts} error={errors.cohort_id} />
              <label className="flex items-center gap-2 text-sm text-ink sm:col-span-2">
                <input type="checkbox" checked={form.start_onboarding} onChange={set("start_onboarding")} className="h-4 w-4 accent-brand-600" />
                Démarrer l'intégration dès maintenant (statut « Intégration »)
              </label>
            </div>
          )}
          <div className="mt-6 flex justify-between gap-3">
            {step === 0 ? (
              <Link href="/pme" className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink">
                Annuler
              </Link>
            ) : (
              <Button type="button" variant="secondary" onClick={() => setStep(step - 1)}>
                Précédent
              </Button>
            )}
            <Button type="submit" loading={busy} disabled={step === 0 && blocking}>
              {step < STEPS.length - 1 ? "Continuer" : duplicates.length ? "Créer malgré les doublons signalés" : "Créer la PME"}
            </Button>
          </div>
        </Card>

        <aside>
          {duplicates.length > 0 ? (
            <Alert tone={blocking ? "danger" : "warning"} title={blocking ? "Cette PME existe déjà" : "Doublons possibles"}>
              <p className="mb-2">
                {blocking
                  ? "Le numéro RCCM ou NCC est déjà utilisé dans l'organisation : la création est impossible."
                  : "Des entreprises au nom proche existent déjà. Vérifiez avant de continuer."}
              </p>
              <ul className="space-y-2">
                {duplicates.map((d) => (
                  <li key={d.id} className="rounded-md bg-white/70 px-3 py-2">
                    {d.accessible ? (
                      <Link href={`/pme/${d.id}`} className="font-medium underline">
                        {d.legal_name}
                      </Link>
                    ) : (
                      <span className="font-medium">{d.legal_name}</span>
                    )}
                    <div className="mt-1 flex flex-wrap gap-1">
                      {d.reasons.map((reason) => (
                        <Badge key={reason} tone={reason === "name" ? "warning" : "danger"}>
                          {reason === "name" ? `Nom proche (${Math.round((d.similarity ?? 0) * 100)} %)` : `Même ${reason.toUpperCase()}`}
                        </Badge>
                      ))}
                      {!d.accessible && <Badge tone="muted">Hors de votre périmètre</Badge>}
                    </div>
                  </li>
                ))}
              </ul>
            </Alert>
          ) : (
            <Card title="Bon à savoir">
              <ul className="list-disc space-y-2 pl-4 text-sm text-muted">
                <li>Seule la raison sociale est obligatoire : la fiche se complète ensuite.</li>
                <li>Les numéros RCCM et NCC permettent d'éviter les doublons dans l'organisation.</li>
                <li>Toutes les modifications sont tracées dans l'historique de la PME.</li>
              </ul>
            </Card>
          )}
        </aside>
      </form>
    </>
  );
}
