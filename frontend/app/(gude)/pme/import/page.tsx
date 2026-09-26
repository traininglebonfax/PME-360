"use client";

/**
 * Import en masse des PME (CSV, V1) : 1. modèle ; 2. aperçu ligne par ligne sans rien créer ; 3. import des lignes
 * valides (les noms proches d'une PME existante seulement sur confirmation) ; 4. bilan.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";

import { Alert, Badge, Button, Card, PageHeader, SelectInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Problem, readCookie, type Schemas } from "@/lib/api";

type Report = Schemas["ImportReport"];
type Row = Schemas["ImportRow"];

const STATUS: Record<string, { label: string; tone: "brand" | "warning" | "danger" | "info" | "muted" }> = {
  VALIDE: { label: "Prête", tone: "info" },
  DOUBLON_PROBABLE: { label: "Nom proche", tone: "warning" },
  ERREUR: { label: "À corriger", tone: "danger" },
  CREEE: { label: "Créée", tone: "brand" },
  IGNOREE: { label: "Ignorée", tone: "muted" },
};

const FIELD_LABELS: Record<string, string> = {
  legal_name: "Raison sociale",
  forme_juridique: "Forme juridique",
  secteur: "Secteur",
  region: "Région",
  date_creation: "Date de création",
  creation_date: "Date de création",
  effectif: "Effectif",
  email: "E-mail",
  phone: "Téléphone",
  website: "Site web",
  dirigeant_fonction: "Fonction du dirigeant",
  dirigeant_email: "E-mail du dirigeant",
  conseiller_email: "Conseiller",
  fichier: "Fichier",
  doublon: "Doublon",
  creation: "Création",
};

async function send(path: string, file: File, fields: Record<string, string>): Promise<Report> {
  if (!readCookie("pme360_csrftoken")) await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields)) if (value) form.append(key, value);
  const response = await fetch(path, {
    method: "POST",
    body: form,
    credentials: "same-origin",
    headers: { "X-CSRFToken": readCookie("pme360_csrftoken") ?? "" },
  });
  const body = await response.json().catch(() => ({ detail: `Erreur ${response.status}` }));
  if (!response.ok) throw new ApiError(response.status, body as Problem);
  return body as Report;
}

export default function PmeImportPage() {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Report | null>(null);
  const [result, setResult] = useState<Report | null>(null);
  const [cohort, setCohort] = useState("");
  const [confirmSimilar, setConfirmSimilar] = useState(false);
  const [busy, setBusy] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const programmes = useQuery({
    queryKey: ["programmes"],
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/programmes");
      return response.ok ? (data as unknown as { results?: Schemas["Programme"][] } | Schemas["Programme"][]) : null;
    },
  });
  const programmeList = Array.isArray(programmes.data) ? programmes.data : programmes.data?.results ?? [];
  const cohorts = programmeList.flatMap((p) => p.cohorts.map((c) => ({ value: c.id, label: `${p.name} · ${c.name}` })));

  async function analyze(selected: File) {
    setError(null);
    setResult(null);
    setBusy("preview");
    try {
      setPreview(await send("/api/v1/pme-import/preview", selected, {}));
    } catch (err) {
      setPreview(null);
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function runImport() {
    if (!file) return;
    setError(null);
    setBusy("import");
    try {
      const report = await send("/api/v1/pme-import", file, { cohort_id: cohort, confirm_similar: confirmSimilar ? "true" : "" });
      setResult(report);
      setPreview(null);
      queryClient.invalidateQueries({ queryKey: ["pmes"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const summary = preview?.summary ?? {};
  const importable = (summary.VALIDE ?? 0) + (confirmSimilar ? summary.DOUBLON_PROBABLE ?? 0 : 0);

  return (
    <>
      <nav className="mb-2 text-sm text-muted">
        <Link href="/pme" className="hover:text-brand-700">
          PME
        </Link>{" "}
        / Import
      </nav>
      <PageHeader title="Importer des PME" subtitle="À partir d'un fichier CSV (Excel : « Enregistrer sous › CSV UTF-8 »). 2 000 lignes au maximum." />

      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <aside className="space-y-4">
          <Card title="1. Préparer le fichier">
            <p className="text-sm text-muted">
              Téléchargez le modèle, remplissez une ligne par entreprise. Seule la raison sociale est obligatoire ; secteur, région et forme juridique
              acceptent le code ou le libellé.
            </p>
            <a href="/api/v1/pme-import/template" className="mt-3 inline-block rounded-lg border border-line px-3 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50">
              Télécharger le modèle
            </a>
          </Card>
          <Card title="2. Vérifier">
            <label htmlFor="import-file" className="mb-2 block text-sm text-muted">
              Fichier CSV
            </label>
            <input
              id="import-file"
              ref={input}
              type="file"
              accept=".csv,text/csv"
              className="block w-full text-sm"
              onChange={(e) => {
                const selected = e.target.files?.[0] ?? null;
                setFile(selected);
                if (selected) void analyze(selected);
              }}
            />
            {busy === "preview" && <p className="mt-2 text-sm text-muted">Analyse du fichier…</p>}
            <p className="mt-2 text-xs text-muted">L'aperçu ne crée rien : chaque ligne est contrôlée comme une saisie manuelle.</p>
          </Card>
          {preview && (
            <Card title="3. Importer">
              <div className="space-y-3 text-sm">
                {cohorts.length > 0 && (
                  <SelectInput label="Inscrire dans une cohorte (facultatif)" value={cohort} onChange={(e) => setCohort(e.target.value)} placeholder="Aucune" options={cohorts} />
                )}
                {(summary.DOUBLON_PROBABLE ?? 0) > 0 && (
                  <label className="flex items-start gap-2">
                    <input type="checkbox" className="mt-0.5 accent-brand-600" checked={confirmSimilar} onChange={(e) => setConfirmSimilar(e.target.checked)} />
                    <span>Importer aussi les {summary.DOUBLON_PROBABLE} ligne(s) au nom proche d'une PME existante (après vérification).</span>
                  </label>
                )}
                <Button className="w-full" disabled={importable === 0} loading={busy === "import"} onClick={() => void runImport()}>
                  Importer {importable} PME
                </Button>
                {(summary.ERREUR ?? 0) > 0 && <p className="text-xs text-muted">Les lignes à corriger sont ignorées : corrigez-les puis réimportez le fichier.</p>}
              </div>
            </Card>
          )}
        </aside>

        <section className="space-y-4">
          {error && <Alert>{error}</Alert>}
          {result && (
            <Alert tone="success" title="Import terminé">
              {result.summary.CREEE ?? 0} PME créée(s), {result.summary.IGNOREE ?? 0} ignorée(s), {result.summary.ERREUR ?? 0} à corriger. Les PME créées
              démarrent en « Intégration ».
            </Alert>
          )}
          {(preview ?? result) && <Rows report={(preview ?? result)!} />}
          {!preview && !result && !error && (
            <Card>
              <p className="text-sm text-muted">Choisissez un fichier pour afficher l'aperçu.</p>
            </Card>
          )}
        </section>
      </div>
    </>
  );
}

function Rows({ report }: { report: Report }) {
  const counts = report.summary;
  return (
    <Card
      title="Lignes du fichier"
      action={
        <div className="flex flex-wrap gap-1.5 text-xs">
          {Object.entries(STATUS).map(([key, s]) => (counts[key] ? <Badge key={key} tone={s.tone}>{`${counts[key]} ${s.label.toLowerCase()}`}</Badge> : null))}
        </div>
      }
    >
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-line text-sm" aria-label="Lignes du fichier">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-2 pr-3">Ligne</th>
              <th className="py-2 pr-3">Raison sociale</th>
              <th className="py-2 pr-3">État</th>
              <th className="py-2">Détail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line align-top">
            {report.rows.map((row: Row) => {
              const status = STATUS[row.status];
              return (
                <tr key={row.line}>
                  <td className="py-2 pr-3 tabular-nums text-muted">{row.line}</td>
                  <td className="py-2 pr-3 font-medium">
                    {row.pme_id ? (
                      <Link href={`/pme/${row.pme_id}`} className="text-brand-700 hover:underline">
                        {row.legal_name}
                      </Link>
                    ) : (
                      row.legal_name || <span className="text-muted">(vide)</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <Badge tone={status?.tone}>{status?.label ?? row.status}</Badge>
                  </td>
                  <td className="py-2 text-xs">
                    {Object.entries(row.errors).map(([field, message]) => (
                      <p key={field} className="text-red-800">
                        <span className="font-medium">{FIELD_LABELS[field] ?? field} :</span> {message}
                      </p>
                    ))}
                    {row.warnings.map((warning) => (
                      <p key={warning} className="text-amber-800">
                        {warning}
                      </p>
                    ))}
                    {row.duplicates.length > 0 && (
                      <p className="text-muted">
                        Proche de : {row.duplicates.map((d) => String((d as { legal_name: string }).legal_name)).join(", ")}
                      </p>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
