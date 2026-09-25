"use client";

/** Écran de vérification : document à gauche, contrôles et décision à droite (Document 1, § 11). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Badge, Button, Card, cx, LoadingBlock, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { CHECK_LABELS, DECISIONS, DOCUMENT_STATUS, formatSize } from "@/lib/documents";
import { formatDate, formatDateTime } from "@/lib/format";

const RESULT_TONES = { OK: "brand", ALERTE: "warning", ECHEC: "danger", NON_DETERMINE: "muted" } as const;

export default function VerificationPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const document = useQuery({
    queryKey: ["document", id],
    queryFn: () => unwrap(api.GET("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } })),
  });
  const [versionNo, setVersionNo] = useState<number | null>(null);
  const current = versionNo ?? document.data?.current_version_no ?? null;
  const version = document.data?.versions.find((v) => v.version_no === current);
  const preview = useQuery({
    queryKey: ["download-url", id, current],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/documents/{document_id}/versions/{version_no}/download-url", {
          params: { path: { document_id: id, version_no: current! } },
        }),
      ),
    enabled: Boolean(version?.downloadable),
    staleTime: 4 * 60_000, // URL signée valable 5 minutes
  });

  if (document.isLoading) return <LoadingBlock />;
  if (document.error) return <Alert>{errorMessage(document.error)}</Alert>;
  const data = document.data!;
  const status = DOCUMENT_STATUS[data.status];
  const previewable = version && [".pdf", ".jpg", ".jpeg", ".png"].includes(version.extension);

  return (
    <>
      <nav className="mb-2 text-sm text-muted">
        <Link href="/verifications" className="hover:text-brand-700">
          Documents à vérifier
        </Link>{" "}
        /{" "}
        <Link href={`/pme/${data.pme.id}?onglet=documents`} className="hover:text-brand-700">
          {data.pme.name}
        </Link>
      </nav>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{data.document_type.name}</h1>
        <Badge tone={status?.tone}>{status?.label ?? data.status}</Badge>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
        <section className="min-h-[32rem] overflow-hidden rounded-xl border border-line bg-gray-100">
          {!version?.downloadable ? (
            <div className="flex h-full items-center justify-center p-8 text-sm text-muted">
              {data.integrity_status === "REJETE_SECURITE" ? "Fichier bloqué par l'antivirus : jamais enregistré." : "Aperçu indisponible."}
            </div>
          ) : preview.data && previewable ? (
            version.extension === ".pdf" ? (
              <iframe title="Aperçu du document" src={preview.data.url} className="h-[75vh] w-full bg-white" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview.data.url} alt={`Aperçu : ${data.document_type.name}`} className="mx-auto max-h-[75vh]" />
            )
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-sm text-muted">
              <p>Aperçu non disponible pour ce format.</p>
              {preview.data && (
                <a href={preview.data.url} className="font-medium text-brand-700 hover:underline">
                  Télécharger le fichier
                </a>
              )}
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <Card title="Fichier">
            {data.versions.length > 1 && (
              <div className="mb-3 flex flex-wrap gap-1">
                {data.versions.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setVersionNo(v.version_no)}
                    className={cx("rounded-md px-2 py-1 text-xs", v.version_no === current ? "bg-brand-50 font-medium text-brand-800" : "bg-gray-100 text-muted")}
                  >
                    v{v.version_no}
                  </button>
                ))}
              </div>
            )}
            {version && (
              <dl className="space-y-1.5 text-sm">
                <Row label="Nom d'origine" value={version.original_filename} />
                <Row label="Taille" value={formatSize(version.size_bytes)} />
                <Row label="Déposé" value={`${formatDateTime(version.created_at)}${version.uploaded_by_name ? ` par ${version.uploaded_by_name}` : ""}`} />
                <Row label="Antivirus" value={version.av_status === "SAIN" ? `Sain (${version.av_engine})` : `Infecté : ${version.av_signature}`} />
                <Row label="Empreinte" value={<span className="font-mono text-xs">{version.sha256.slice(0, 16)}…</span>} />
              </dl>
            )}
            {version && version.checks.length > 0 && (
              <ul className="mt-3 space-y-1.5 border-t border-line pt-3">
                {version.checks.map((check) => (
                  <li key={check.check_code} className="flex items-start gap-2 text-sm">
                    <Badge tone={RESULT_TONES[check.result as keyof typeof RESULT_TONES]}>{CHECK_LABELS[check.check_code] ?? check.check_code}</Badge>
                    <span className="text-muted">{check.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <DecisionCard
            key={`${data.id}-${data.current_version_no}-${data.status}`}
            document={data}
            onDone={() => {
              queryClient.invalidateQueries({ queryKey: ["verifications"] });
              queryClient.invalidateQueries({ queryKey: ["document", id] });
              queryClient.invalidateQueries({ queryKey: ["folder", data.pme.id] });
              router.push("/verifications");
            }}
          />
        </aside>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-ink">{value}</dd>
    </div>
  );
}

function DecisionCard({ document, onDone }: { document: Schemas["DocumentDetail"]; onDone: () => void }) {
  const [decision, setDecision] = useState<string>("CONFORME");
  // Initialisé une fois depuis le document ; le parent remonte ce composant (key) quand le document change.
  const [form, setForm] = useState(() => ({
    reason: document.decision_reason ?? "",
    period_start: document.period_start ?? document.deadline?.period_start?.toString() ?? "",
    period_end: document.period_end ?? document.deadline?.period_end?.toString() ?? "",
    issued_at: document.issued_at ?? "",
    expires_at: document.expires_at ?? "",
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const verify = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/documents/{document_id}/verify", {
          params: { path: { document_id: document.id } },
          body: {
            decision: decision as Schemas["VerifyRequest"]["decision"],
            reason: form.reason,
            period_start: form.period_start || null,
            period_end: form.period_end || null,
            issued_at: form.issued_at || null,
            expires_at: form.expires_at || null,
          },
        }),
      ),
    onSuccess: onDone,
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });
  if (document.integrity_status !== "SAIN") return null;
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });

  return (
    <Card title="Décision">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          verify.mutate();
        }}
      >
        {document.deadline && (
          <p className="text-xs text-muted">
            Échéance attendue : {document.deadline.period_label} (du {formatDate(document.deadline.period_start as string)} au{" "}
            {formatDate(document.deadline.period_end as string)})
          </p>
        )}
        <div className="grid grid-cols-2 gap-2">
          <TextInput label="Début de période" type="date" value={form.period_start} onChange={set("period_start")} />
          <TextInput label="Fin de période" type="date" value={form.period_end} onChange={set("period_end")} error={errors.period_end} />
          <TextInput label="Date de délivrance" type="date" value={form.issued_at} onChange={set("issued_at")} />
          <TextInput label="Valable jusqu'au" type="date" value={form.expires_at} onChange={set("expires_at")} error={errors.expires_at} />
        </div>
        <fieldset className="space-y-1">
          <legend className="mb-1 text-sm font-medium">Décision</legend>
          {DECISIONS.map((option) => (
            <label key={option.value} className="flex items-center gap-2 text-sm">
              <input type="radio" name="decision" className="accent-brand-600" checked={decision === option.value} onChange={() => setDecision(option.value)} />
              {option.label}
            </label>
          ))}
        </fieldset>
        <TextInput
          label={decision === "CONFORME" ? "Commentaire (facultatif)" : "Motif pour la PME (obligatoire, langage simple)"}
          value={form.reason}
          onChange={set("reason")}
          error={errors.reason}
          required={decision !== "CONFORME"}
        />
        {verify.error && !(verify.error instanceof ApiError && verify.error.code === "validation_error") && <Alert>{errorMessage(verify.error)}</Alert>}
        <Button type="submit" className="w-full" loading={verify.isPending}>
          Enregistrer la décision
        </Button>
        <p className="text-xs text-muted">La PME est prévenue ; un document conforme relève le score courant de la PME.</p>
      </form>
    </Card>
  );
}
