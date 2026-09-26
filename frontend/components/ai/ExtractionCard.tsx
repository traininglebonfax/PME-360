"use client";

/**
 * Lecture IA d'un document (Document 4, § 4 à 7) : type reconnu, champs extraits avec leur confiance, revue
 * humaine (valider, corriger avec justification, rejeter). L'extraction n'est jamais une décision de conformité.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Card, TextInput } from "@/components/ui";
import { confidenceTone, EXTRACTION_STATUS, fieldInputValue, formatConfidence, formatFieldValue, parseFieldValue } from "@/lib/ai";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { hasPermission, useMe } from "@/lib/session";

type Extraction = Schemas["Extraction"];
type Mode = "view" | "correct" | "reject";

const REVIEWED = ["VALIDEE", "CORRIGEE", "REJETEE"];

export function ExtractionCard({ documentId, typeName, onReviewed }: { documentId: string; typeName: string; onReviewed?: () => void }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const key = ["extraction", documentId];
  const extraction = useQuery({
    queryKey: key,
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/documents/{document_id}/extraction", {
        params: { path: { document_id: documentId } },
      });
      if (response.status === 204) return null;
      if (!response.ok)
        throw new ApiError(response.status, {
          detail: "Analyse IA indisponible.",
        });
      return data as Extraction;
    },
  });
  const reanalyze = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/documents/{document_id}/reanalyze", {
          params: { path: { document_id: documentId } },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });

  if (extraction.isLoading) return <Card title="Lecture IA">Chargement…</Card>;
  if (extraction.error) return <Alert>{errorMessage(extraction.error)}</Alert>;
  const data = extraction.data;
  const canReview = hasPermission(me, "ai.review");

  if (!data)
    return (
      <Card title="Lecture IA">
        <p className="text-sm text-muted">Ce document n'a pas encore été analysé par l'IA.</p>
        <Button variant="secondary" className="mt-3" loading={reanalyze.isPending} onClick={() => reanalyze.mutate()}>
          Lancer l'analyse
        </Button>
        {reanalyze.error && <p className="mt-2 text-sm text-red-700">{errorMessage(reanalyze.error)}</p>}
      </Card>
    );

  const status = EXTRACTION_STATUS[data.status];
  const confidence = data.confidence === null ? null : Number(data.confidence);
  const classification = data.classification_confidence === null ? null : Number(data.classification_confidence);

  return (
    <Card title="Lecture IA" action={<Badge tone={status?.tone}>{status?.label ?? data.status}</Badge>}>
      <div className="space-y-3 text-sm" data-testid="extraction-card">
        <dl className="space-y-1.5">
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Type reconnu</dt>
            <dd className="text-right">
              {data.classified_type ? (
                <>
                  {data.classified_type === data.expected_type ? (
                    <span>{typeName}</span>
                  ) : (
                    <span className="font-medium text-red-700" title="Différent du type attendu">
                      {data.classified_type} (attendu : {typeName})
                    </span>
                  )}
                  {classification !== null && <span className="ml-1 text-xs text-muted">({formatConfidence(classification)})</span>}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Confiance du document</dt>
            <dd>
              <Badge tone={confidenceTone(confidence)}>{formatConfidence(confidence)}</Badge>
            </dd>
          </div>
        </dl>
        {data.reason && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <span className="font-medium">Pourquoi une vérification : </span>
            {data.reason}
          </p>
        )}
        {data.status === "NON_ANALYSEE" ? (
          <p className="text-muted">Aucune lecture automatique : vérifiez le document visuellement.</p>
        ) : (
          data.fields_detail.length === 0 && (
            <p className="text-muted">Pas de champs à extraire pour « {typeName} » : seule la classification est proposée.</p>
          )
        )}
        {data.status !== "NON_ANALYSEE" && (
          <FieldsReview
            key={`${data.id}-${data.status}`}
            documentId={documentId}
            extraction={data}
            canReview={canReview}
            onSaved={(updated) => {
              queryClient.setQueryData(key, updated);
              queryClient.invalidateQueries({ queryKey: ["verifications"] });
              onReviewed?.();
            }}
          />
        )}
        {REVIEWED.includes(data.status) && (
          <p className="text-xs text-muted">
            Revue par {data.reviewed_by_name || "—"} le {formatDateTime(data.reviewed_at)}
            {data.review_comment && ` : « ${data.review_comment} »`}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3 text-xs">
          {data.extraction_analysis && canReview && (
            <Link href={`/ia/analyses/${data.extraction_analysis}`} className="font-medium text-brand-700 hover:underline">
              Voir l'analyse IA
            </Link>
          )}
          {data.classification_analysis && canReview && (
            <Link href={`/ia/analyses/${data.classification_analysis}`} className="text-brand-700 hover:underline">
              Classification
            </Link>
          )}
          <button className="ml-auto text-muted hover:text-ink" disabled={reanalyze.isPending} onClick={() => reanalyze.mutate()}>
            {reanalyze.isPending ? "Analyse en cours…" : "Relancer l'analyse"}
          </button>
        </div>
        {reanalyze.error && <p className="text-xs text-red-700">{errorMessage(reanalyze.error)}</p>}
      </div>
    </Card>
  );
}

function FieldsReview({
  documentId,
  extraction,
  canReview,
  onSaved,
}: {
  documentId: string;
  extraction: Extraction;
  canReview: boolean;
  onSaved: (e: Extraction) => void;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(extraction.fields_detail.map((f) => [f.name, fieldInputValue(f.value)])),
  );
  const [comment, setComment] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const reviewed = REVIEWED.includes(extraction.status);
  const save = useMutation({
    mutationFn: (status: Schemas["ExtractionReviewStatusEnum"]) => {
      const corrections: Record<string, unknown> = {};
      if (status === "CORRIGEE")
        for (const field of extraction.fields_detail) {
          const next = parseFieldValue(values[field.name] ?? "", field.type);
          if (JSON.stringify(next) !== JSON.stringify(field.value ?? null)) corrections[field.name] = next;
        }
      return unwrap(
        api.POST("/api/v1/documents/{document_id}/extraction/review", {
          params: { path: { document_id: documentId } },
          body: { status, corrections, comment },
        }),
      );
    },
    onSuccess: (updated) => {
      setMode("view");
      onSaved(updated);
    },
    onError: (error) => setErrors(error instanceof ApiError ? error.fieldErrors() : {}),
  });

  return (
    <div className="space-y-3">
      {extraction.fields_detail.length > 0 && (
        <table className="w-full text-sm">
          <tbody className="divide-y divide-line align-top">
            {extraction.fields_detail.map((field) => (
              <tr key={field.name}>
                <th scope="row" className="py-1.5 pr-2 text-left font-normal text-muted">
                  {field.label}
                  {field.critical && (
                    <span className="ml-1 text-red-700" title="Champ critique">
                      *
                    </span>
                  )}
                </th>
                <td className="py-1.5 text-right">
                  {mode === "correct" ? (
                    <input
                      aria-label={field.label}
                      className="w-full rounded-md border border-line px-2 py-1 text-right text-sm"
                      value={values[field.name] ?? ""}
                      placeholder={field.type === "date" ? "AAAA-MM-JJ" : undefined}
                      onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
                    />
                  ) : (
                    <>
                      <span className="text-ink">{formatFieldValue(field.value, field.type)}</span>
                      <span className="ml-1.5 inline-block">
                        {field.corrected ? (
                          <Badge tone="brand">corrigé</Badge>
                        ) : (
                          <Badge tone={confidenceTone(field.confidence, field.critical ? 0.9 : 0.85)}>{formatConfidence(field.confidence)}</Badge>
                        )}
                      </span>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {extraction.fields_detail.some((f) => f.critical) && <p className="text-xs text-muted">* champ critique : confiance de 90 % exigée.</p>}
      {errors.corrections && <p className="text-sm text-red-700">{errors.corrections}</p>}

      {canReview && !reviewed && mode === "view" && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => save.mutate("VALIDEE")} loading={save.isPending && save.variables === "VALIDEE"}>
            Valider la lecture
          </Button>
          {extraction.fields_detail.length > 0 && (
            <Button variant="secondary" onClick={() => setMode("correct")}>
              Corriger
            </Button>
          )}
          <Button variant="ghost" onClick={() => setMode("reject")}>
            Rejeter
          </Button>
        </div>
      )}
      {canReview && reviewed && mode === "view" && extraction.fields_detail.length > 0 && (
        <button className="text-xs text-brand-700 hover:underline" onClick={() => setMode("correct")}>
          Modifier la lecture validée
        </button>
      )}
      {mode !== "view" && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(mode === "correct" ? "CORRIGEE" : "REJETEE");
          }}
        >
          <TextInput
            label={mode === "correct" ? "Justification de la correction (obligatoire)" : "Motif du rejet (obligatoire)"}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            error={errors.comment}
            required
          />
          <div className="flex gap-2">
            <Button type="submit" variant={mode === "reject" ? "danger" : "primary"} loading={save.isPending}>
              {mode === "correct" ? "Enregistrer les corrections" : "Rejeter la lecture"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode("view")}>
              Annuler
            </Button>
          </div>
        </form>
      )}
      {save.error && !(save.error instanceof ApiError && save.error.code === "validation_error") && <Alert>{errorMessage(save.error)}</Alert>}
    </div>
  );
}
