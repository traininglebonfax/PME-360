"use client";

/**
 * « Mon plan » (portail PME) : le plan proposé par GUDE-PME à accepter, puis les actions par horizon,
 * avec le pourquoi et les documents à déposer (Document 7, § 4.6 ; Document 9, § 2).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PmeShell } from "@/components/PmeShell";
import { PhaseBoard } from "@/components/plans/PlanTab";
import { Alert, Button, Card, EmptyState, LoadingBlock } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { hasPermission, type Me } from "@/lib/session";

export default function PmePlanPage() {
  return <PmeShell title="Mon plan d'accompagnement" subtitle="Les actions proposées par votre conseiller, dans l'ordre où les mener.">{(me) => <PlanView me={me} />}</PmeShell>;
}

function PlanView({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const pmeId = me.pme_ids[0];
  const plan = useQuery({
    queryKey: ["plan", pmeId],
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/pmes/{pme_id}/plan", { params: { path: { pme_id: pmeId } } });
      if (response.status === 204) return null;
      if (!response.ok) throw new ApiError(response.status, { detail: "Plan indisponible." });
      return data as Schemas["PlanDetail"];
    },
    enabled: Boolean(pmeId),
  });
  const accept = useMutation({
    mutationFn: (planId: string) =>
      unwrap(api.POST("/api/v1/plans/{plan_id}/transition", { params: { path: { plan_id: planId } }, body: { action: "accept", reason: "" } })),
    onSuccess: (updated) => {
      queryClient.setQueryData(["plan", pmeId], updated);
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (plan.isLoading) return <LoadingBlock />;
  if (plan.error) return <Alert>{errorMessage(plan.error)}</Alert>;
  const data = plan.data;
  if (!data)
    return (
      <EmptyState title="Pas encore de plan">
        Votre conseiller prépare votre plan d'accompagnement à partir de votre diagnostic. Vous serez prévenu dès qu'il sera prêt.
      </EmptyState>
    );
  const progress = data.progress as { total: number; done: number; rate: number | null };
  const toAccept = data.status === "EN_VALIDATION";

  return (
    <>
      {toAccept ? (
        <Card title="Votre plan est prêt">
          <p className="text-sm text-ink">
            Votre conseiller vous propose {progress.total} action(s) à démarrer à partir du {formatDate(data.horizon_start)}. Lisez-les, puis
            acceptez le plan pour commencer. Vous pourrez en parler avec votre conseiller à tout moment.
          </p>
          {hasPermission(me, "plan.accept") ? (
            <Button className="mt-3" loading={accept.isPending} onClick={() => accept.mutate(data.id)}>
              J'accepte le plan
            </Button>
          ) : (
            <p className="mt-2 text-xs text-muted">Seule la direction de l'entreprise peut accepter le plan.</p>
          )}
          {accept.error && <Alert>{errorMessage(accept.error)}</Alert>}
        </Card>
      ) : (
        <Card title="Mon avancement">
          <p className="text-sm">
            {progress.done} action(s) terminée(s) sur {progress.total}
            {data.accepted_at && <span className="text-muted"> · plan accepté le {formatDate(data.accepted_at)}</span>}
          </p>
          {progress.rate !== null && (
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100">
              <div className="h-full bg-brand-600" style={{ width: `${Math.round(progress.rate * 100)}%` }} />
            </div>
          )}
          <p className="mt-2 text-xs text-muted">Chaque action terminée, avec ses documents vérifiés, fait progresser votre score.</p>
        </Card>
      )}
      <PhaseBoard actions={data.actions} actionHref={(id) => `/espace/plan/${id}`} pmeView />
    </>
  );
}
