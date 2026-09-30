"use client";

/**
 * « Mes documents » (portail PME) : ce qu'il faut déposer, avant quand, et ce qui a été validé ou refusé
 * (Document 1, § 10). Dépôt par fichier ou par photo depuis le téléphone.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ComplianceSummary, DeadlineList } from "@/components/documents/DocumentsTab";
import { UploadButton } from "@/components/documents/UploadButton";
import { PmeShell } from "@/components/PmeShell";
import { Alert, Badge, Card, LoadingBlock, SelectInput } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { DOCUMENT_STATUS, FOLDER_STATE } from "@/lib/documents";
import { formatDate } from "@/lib/format";

export default function PmeDocumentsPage() {
  return (
    <PmeShell title="Mes documents" subtitle="Déposez vos justificatifs : votre conseiller les vérifie et vous répond ici.">
      {(me) => <Content pmeId={me.pme_ids[0]} />}
    </PmeShell>
  );
}

function Content({ pmeId }: { pmeId: string }) {
  const folder = useQuery({
    queryKey: ["folder", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/compliance-folder", { params: { path: { pme_id: pmeId } } })),
  });
  const deadlines = useQuery({
    queryKey: ["deadlines", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/deadlines", { params: { path: { pme_id: pmeId } } })),
  });
  if (folder.isLoading) return <LoadingBlock />;
  if (folder.error) return <Alert>{errorMessage(folder.error)}</Alert>;
  const items = folder.data!.categories.flatMap((c) => c.items);

  return (
    <>
      <Card title="À transmettre">
        {deadlines.data ? (
          <DeadlineList
            pmeId={pmeId}
            deadlines={deadlines.data}
            canUpload
            emptyMessage="Aucune échéance pour le moment : elles s'ouvrent dès que votre conseiller démarre votre diagnostic. Vous pouvez déjà déposer vos documents ci-dessous."
          />
        ) : (
          <LoadingBlock />
        )}
      </Card>
      <OtherDocument pmeId={pmeId} />
      <Card title="Mon dossier">
        <div className="mb-4">
          <ComplianceSummary rate={folder.data!.rate} />
        </div>
        {items.length === 0 && (
          <p className="text-sm text-muted">
            La liste des pièces exigées pour votre entreprise sera établie après la validation de votre diagnostic. En attendant, utilisez
            « Déposer un autre document ».
          </p>
        )}
        <ul className="divide-y divide-line">
          {items.map((item) => {
            const type = item.document_type as { code: string; name: string; guidance: string };
            const state = FOLDER_STATE[item.state];
            const latest = item.documents[0];
            return (
              <li key={type.code} className="space-y-2 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{type.name}</p>
                  <Badge tone={state?.tone}>{state?.label ?? item.state}</Badge>
                </div>
                {type.guidance && <p className="text-xs text-muted">{type.guidance}</p>}
                {latest && (
                  <p className="text-xs text-muted">
                    Dernier dépôt le {formatDate(latest.created_at)} : {DOCUMENT_STATUS[latest.status]?.label.toLowerCase() ?? latest.status}
                    {latest.decision_reason && <span className="block text-ink">→ « {latest.decision_reason} »</span>}
                  </p>
                )}
                {item.state !== "CONFORME" && item.state !== "EN_VERIFICATION" && (
                  <UploadButton pmeId={pmeId} fields={{ document_type: type.code, document_id: latest?.id }} label="Déposer un fichier" />
                )}
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-xs text-muted">
          Formats acceptés : PDF, Word, Excel, CSV, JPG, PNG, HEIC (25 Mo maximum). Masquez les données personnelles de vos salariés.
        </p>
      </Card>
    </>
  );
}

/** Dépôt libre : un document que la PME a sous la main, même s'il n'est pas (encore) demandé. */
function OtherDocument({ pmeId }: { pmeId: string }) {
  const [type, setType] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const types = useQuery({
    queryKey: ["document-types"],
    queryFn: () => unwrap(api.GET("/api/v1/document-types")),
  });
  const options = (types.data ?? [])
    .slice()
    .sort((a, b) => a.category_name.localeCompare(b.category_name, "fr") || a.name.localeCompare(b.name, "fr"))
    .map((t) => ({ value: t.code, label: `${t.category_name} · ${t.name}` }));
  const guidance = types.data?.find((t) => t.code === type)?.guidance;
  return (
    <Card title="Déposer un autre document">
      <p className="mb-3 text-sm text-muted">
        Vous avez un justificatif sous la main (statuts, attestation, états financiers…) ? Choisissez son type et déposez-le : votre
        conseiller le vérifiera.
      </p>
      <div className="space-y-3">
        <SelectInput
          label="Type de document"
          value={type}
          onChange={(event) => {
            setType(event.target.value);
            setSent(null);
          }}
          options={options}
          placeholder={types.isLoading ? "Chargement…" : "— Choisir le type —"}
          hint={guidance || undefined}
        />
        {type && (
          <UploadButton
            key={type}
            pmeId={pmeId}
            fields={{ document_type: type }}
            label="Choisir le fichier"
            onDone={() => {
              setSent(options.find((o) => o.value === type)?.label ?? type);
              setType("");
            }}
          />
        )}
        {sent && <p className="text-sm text-brand-700">✓ {sent} : document reçu, il apparaît dans « Mon dossier » et va être vérifié.</p>}
      </div>
    </Card>
  );
}
