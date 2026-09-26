"use client";

/**
 * Revue par critère (Document 1, § 4, étape 5 ; RM-05, RM-06) : valider, modifier (justification obligatoire)
 * ou déclarer non applicable ; puis validation du diagnostic → snapshot figé.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { ConfidenceBadge, DimensionBars } from "@/components/scoring/HealthCheck";
import { Alert, Badge, Button, Card, cx, LoadingBlock, TextInput } from "@/components/ui";
import { confidenceTone, formatConfidence, SUGGESTION_STATUS } from "@/lib/ai";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import {
  type CriterionResult,
  type EngineResult,
  formatPercent,
  formatScore,
  LENS_LABELS,
  PRIORITY_LABELS,
  SOURCE_LABELS,
} from "@/lib/scoring";

type ReviewCriterion = Schemas["ReviewCriterion"];

const ASSESSMENT_LABELS: Record<string, string> = { VALIDE: "Validé", MODIFIE: "Modifié", NON_APPLICABLE: "Non applicable" };

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const key = ["review", id];
  const review = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/diagnostics/{diagnostic_id}/review", { params: { path: { diagnostic_id: id } } })),
  });
  const [openCode, setOpenCode] = useState<string | null>(null);
  const [confirmBulk, setConfirmBulk] = useState(false);
  const [reopenReason, setReopenReason] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });

  const accept = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/review/accept-remaining", { params: { path: { diagnostic_id: id } } })),
    onSuccess: () => {
      setConfirmBulk(false);
      refresh();
    },
  });
  const validate = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/validate", { params: { path: { diagnostic_id: id } } })),
    onSuccess: (diagnostic) => {
      queryClient.invalidateQueries({ queryKey: ["health", diagnostic.pme.id] });
      router.push(`/pme/${diagnostic.pme.id}?onglet=diagnostic`);
    },
  });
  const prediagnose = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/suggestions", { params: { path: { diagnostic_id: id } } })),
    onSuccess: refresh,
  });
  const reopen = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/reopen", { params: { path: { diagnostic_id: id } }, body: { reason: reopenReason } })),
    onSuccess: () => router.push(`/diagnostics/${id}`),
  });

  if (review.isLoading) return <LoadingBlock />;
  if (review.error) return <Alert>{errorMessage(review.error)}</Alert>;
  const data = review.data!;
  const preview = data.preview as unknown as EngineResult;
  const editable = data.diagnostic.status === "EN_REVUE";
  const criteria = data.dimensions.flatMap((d) => d.criteria);
  const suggested = criteria.filter((c) => c.suggestion).length;
  const disagreements = criteria.filter(
    (c) => c.suggestion?.proposed_level != null && c.suggestion.status === "PROPOSEE" && c.suggestion.proposed_level !== (c.result as unknown as CriterionResult).level_uncapped,
  ).length;

  return (
    <>
      <nav className="mb-2 text-sm text-muted">
        <Link href={`/pme/${data.diagnostic.pme.id}`} className="hover:text-brand-700">
          {data.diagnostic.pme.name}
        </Link>{" "}
        / Revue du diagnostic
      </nav>
      <h1 className="mb-6 text-2xl font-semibold">Revue et validation</h1>
      {!editable && (
        <div className="mb-4">
          <Alert tone="info">Ce diagnostic n'est pas en revue (statut : {data.diagnostic.status}).</Alert>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          {data.dimensions.map((dimension) => (
            <Card
              key={dimension.code}
              title={dimension.name}
              action={
                <span className="text-sm text-muted">
                  {formatScore((dimension.result as { score: number | null }).score)}/100
                </span>
              }
            >
              <ul className="divide-y divide-line">
                {dimension.criteria.map((criterion) => (
                  <CriterionRow
                    key={criterion.code}
                    criterion={criterion}
                    open={openCode === criterion.code}
                    editable={editable}
                    onToggle={() => setOpenCode(openCode === criterion.code ? null : criterion.code)}
                    diagnosticId={id}
                    onSaved={() => {
                      setOpenCode(null);
                      refresh();
                    }}
                  />
                ))}
              </ul>
            </Card>
          ))}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <Card title="Résultat provisoire">
            <p className="text-4xl font-semibold">
              {formatScore(preview.global_score)}
              <span className="text-base font-normal text-muted">/100</span>
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <ConfidenceBadge value={preview.confidence} label={preview.confidence_label} />
              <Badge tone="neutral">{PRIORITY_LABELS[preview.priority.priority]}</Badge>
            </div>
            <p className="mt-2 text-sm text-muted">
              {preview.maturity.level ? `N${preview.maturity.level} · ${preview.maturity.label}` : "Niveau non déterminé"}
              {preview.maturity.capped && " (plafonné)"}
            </p>
            <div className="mt-4">
              <DimensionBars result={preview} />
            </div>
          </Card>
          <Card title="Pré-diagnostic IA">
            <p className="text-sm text-muted">
              {suggested === 0
                ? "Aucune proposition pour l'instant. L'IA propose un niveau par critère à partir des réponses et des preuves ; vous décidez."
                : `${suggested} critère(s) avec une proposition${disagreements ? `, dont ${disagreements} différente(s) du niveau déclaré` : ""}.`}
            </p>
            {editable && (
              <Button variant="secondary" className="mt-3 w-full" loading={prediagnose.isPending} onClick={() => prediagnose.mutate()}>
                {suggested === 0 ? "Lancer le pré-diagnostic" : "Relancer le pré-diagnostic"}
              </Button>
            )}
            {prediagnose.error && <p className="mt-2 text-sm text-red-700">{errorMessage(prediagnose.error)}</p>}
          </Card>
          {editable && (
            <Card title="Validation">
              <p className="text-sm text-muted">
                {data.pending.length === 0
                  ? "Tous les critères évalués sont revus."
                  : `${data.pending.length} critère(s) évalué(s) restent à revoir.`}
              </p>
              {data.pending.length > 0 && (
                <div className="mt-3 space-y-2">
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-0.5 accent-brand-600" checked={confirmBulk} onChange={(e) => setConfirmBulk(e.target.checked)} />
                    <span>Je confirme accepter les niveaux déclarés des {data.pending.length} critères restants.</span>
                  </label>
                  <Button variant="secondary" className="w-full" disabled={!confirmBulk} loading={accept.isPending} onClick={() => accept.mutate()}>
                    Accepter les critères restants
                  </Button>
                </div>
              )}
              <Button className="mt-3 w-full" disabled={data.pending.length > 0} loading={validate.isPending} onClick={() => validate.mutate()}>
                Valider le diagnostic
              </Button>
              {validate.error && (
                <div className="mt-3">
                  <Alert>{errorMessage(validate.error)}</Alert>
                </div>
              )}
              <p className="mt-2 text-xs text-muted">La validation fige le snapshot : il ne pourra plus être modifié.</p>
              <div className="mt-4 border-t border-line pt-4">
                <TextInput label="Renvoyer en collecte (motif)" value={reopenReason} onChange={(e) => setReopenReason(e.target.value)} />
                <Button variant="ghost" className="mt-2" disabled={!reopenReason.trim()} loading={reopen.isPending} onClick={() => reopen.mutate()}>
                  Renvoyer à la PME
                </Button>
              </div>
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}

function CriterionRow({
  criterion,
  open,
  editable,
  onToggle,
  diagnosticId,
  onSaved,
}: {
  criterion: ReviewCriterion;
  open: boolean;
  editable: boolean;
  onToggle: () => void;
  diagnosticId: string;
  onSaved: () => void;
}) {
  const result = criterion.result as unknown as CriterionResult;
  const assessment = criterion.assessment;
  const suggestion = criterion.suggestion;
  const [level, setLevel] = useState<number | null>(assessment?.level_final ?? result.level_uncapped);
  const [comment, setComment] = useState(assessment?.comment ?? "");
  const [corroborated, setCorroborated] = useState(assessment?.corroborated ?? false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: (status: Schemas["AssessmentStatusEnum"]) =>
      unwrap(
        api.POST("/api/v1/diagnostics/{diagnostic_id}/review/{criterion_code}", {
          params: { path: { diagnostic_id: diagnosticId, criterion_code: criterion.code } },
          body: { status, level_final: status === "MODIFIE" ? level : null, comment, corroborated },
        }),
      ),
    onSuccess: onSaved,
    onError: (error) => setErrors(error instanceof ApiError ? error.fieldErrors() : {}),
  });
  const isMetric = result.source === "INDICATEURS" || Boolean(result.metrics?.length);
  const changed = level !== result.level_uncapped;

  return (
    <li className="py-3">
      <button onClick={onToggle} className="flex w-full items-start justify-between gap-3 text-left" aria-expanded={open}>
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">
            <span className="mr-1.5 font-mono text-xs text-muted">{criterion.code}</span>
            {criterion.name}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge tone="muted">{LENS_LABELS[criterion.lens]}</Badge>
            {criterion.is_critical && <Badge tone="warning">Critique</Badge>}
            {result.capped && <Badge tone="info">Plafonné sans preuve (niv. {result.level_uncapped} déclaré)</Badge>}
            {result.status === "NON_EVALUE" && <Badge tone="muted">Non renseigné</Badge>}
            {assessment && (
              <Badge tone={assessment.status === "MODIFIE" ? "warning" : "brand"}>{ASSESSMENT_LABELS[assessment.status]}</Badge>
            )}
            {suggestion?.proposed_level != null && !assessment && suggestion.proposed_level !== result.level_uncapped && (
              <Badge tone="info">IA propose niv. {suggestion.proposed_level}</Badge>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold tabular-nums">{result.level !== null ? `niv. ${result.level}` : formatScore(result.score)}</p>
          <p className="text-xs text-muted">{result.source ? SOURCE_LABELS[result.source] ?? result.source : "—"}</p>
          <p className="text-xs text-muted">confiance {formatPercent(result.confidence)}</p>
        </div>
      </button>

      {open && (
        <div className="mt-3 space-y-3 rounded-lg bg-gray-50 p-4 text-sm">
          {(criterion.answers as { question: string; answer: string; source: string }[]).map((answer, index) => (
            <div key={index}>
              <p className="text-muted">{answer.question}</p>
              <p className="font-medium">
                {answer.answer} <span className="text-xs font-normal text-muted">({SOURCE_LABELS[answer.source] ?? answer.source})</span>
              </p>
            </div>
          ))}
          {suggestion && (
            <div className="rounded-md border border-sky-200 bg-sky-50 p-3" data-testid="suggestion">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium text-sky-900">
                  Proposition IA : {suggestion.proposed_level != null ? `niv. ${suggestion.proposed_level}` : "pas de niveau (preuves insuffisantes)"}
                </span>
                <Badge tone={confidenceTone(Number(suggestion.confidence), 0.75)}>confiance {formatConfidence(Number(suggestion.confidence))}</Badge>
                <Badge tone={SUGGESTION_STATUS[suggestion.status]?.tone}>{SUGGESTION_STATUS[suggestion.status]?.label ?? suggestion.status}</Badge>
              </div>
              <p className="mt-1 text-sky-900">{suggestion.justification}</p>
              {suggestion.sources.length > 0 && <p className="mt-1 text-xs text-sky-800">Sources : {suggestion.sources.join(" · ")}</p>}
              {editable && !isMetric && suggestion.proposed_level != null && suggestion.proposed_level !== level && (
                <button className="mt-2 text-xs font-medium text-brand-700 hover:underline" onClick={() => setLevel(suggestion.proposed_level)}>
                  Reprendre ce niveau (à justifier)
                </button>
              )}
            </div>
          )}
          {isMetric && <p className="text-muted">Critère calculé à partir des indicateurs financiers (score {formatScore(result.score)}/100).</p>}
          {assessment?.comment && (
            <p className="text-muted">
              Commentaire de revue : <span className="text-ink">{assessment.comment}</span>
            </p>
          )}
          {editable && (
            <>
              {!isMetric && (
                <div>
                  <p className="mb-1.5 font-medium">Niveau retenu</p>
                  <div className="space-y-1">
                    {criterion.rubric.map((anchor, index) => (
                      <label
                        key={index}
                        className={cx(
                          "flex cursor-pointer items-start gap-2 rounded-md border px-3 py-1.5",
                          level === index ? "border-brand-600 bg-white" : "border-transparent hover:bg-white",
                        )}
                      >
                        <input type="radio" name={`lvl-${criterion.code}`} className="mt-0.5 accent-brand-600" checked={level === index} onChange={() => setLevel(index)} />
                        <span>
                          <span className="font-mono text-xs text-muted">niv. {index}</span> {anchor}
                          {index === result.level_uncapped && <span className="ml-1 text-xs text-muted">(déclaré)</span>}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              <TextInput
                label={changed ? "Justification (obligatoire)" : "Commentaire"}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                error={errors.comment ?? errors.level_final}
              />
              {!isMetric && (
                <label className="flex items-center gap-2">
                  <input type="checkbox" className="accent-brand-600" checked={corroborated} onChange={(e) => setCorroborated(e.target.checked)} />
                  Déclaration corroborée (entretien, visite)
                </label>
              )}
              {save.error && !(save.error instanceof ApiError && save.error.code === "validation_error") && <Alert>{errorMessage(save.error)}</Alert>}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => save.mutate(changed ? "MODIFIE" : "VALIDE")} loading={save.isPending}>
                  {changed ? "Enregistrer la modification" : "Valider le niveau déclaré"}
                </Button>
                <Button variant="ghost" onClick={() => save.mutate("NON_APPLICABLE")}>
                  Non applicable
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </li>
  );
}
