"use client";

/**
 * Échanges sur une action (Document 3, § 3.6) : le conseiller choisit « interne GUDE-PME » ou « partagé avec la
 * PME » ; la PME ne voit et n'écrit que des messages partagés. Les messages ne sont jamais modifiés.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Alert, Badge, Button, Card, cx } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type Visibility = Schemas["VisibilityEnum"];

export function ActionComments({ actionId, pmeView = false }: { actionId: string; pmeView?: boolean }) {
  const queryClient = useQueryClient();
  const key = ["action-comments", actionId];
  const comments = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/actions/{action_id}/comments", { params: { path: { action_id: actionId } } })),
  });
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("INTERNE_GUDE"); // prudence : partager est un choix explicite
  const send = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/actions/{action_id}/comments", {
          params: { path: { action_id: actionId } },
          body: { body, visibility: pmeView ? "PARTAGE_PME" : visibility },
        }),
      ),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({ queryKey: key });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (body.trim()) send.mutate();
  }

  return (
    <Card title={pmeView ? "Échanges avec mon conseiller" : "Échanges"}>
      {comments.isLoading ? (
        <p className="text-sm text-muted">Chargement…</p>
      ) : comments.error ? (
        <Alert>{errorMessage(comments.error)}</Alert>
      ) : comments.data!.length === 0 ? (
        <p className="text-sm text-muted">{pmeView ? "Posez ici vos questions sur cette action." : "Aucun échange pour l'instant."}</p>
      ) : (
        <ol className="space-y-3" aria-label="Échanges">
          {comments.data!.map((comment) => {
            const internal = comment.visibility === "INTERNE_GUDE";
            return (
              <li
                key={comment.id}
                className={cx(
                  "rounded-lg px-3 py-2 text-sm",
                  internal ? "border border-dashed border-amber-300 bg-amber-50" : comment.author_is_pme ? "bg-gray-50" : "bg-brand-50",
                )}
              >
                <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  <span className="font-medium text-ink">{comment.author_name}</span>
                  {comment.author_is_pme && <span>(PME)</span>}
                  <span>· {formatDateTime(comment.created_at)}</span>
                  {!pmeView && internal && <Badge tone="warning">Interne GUDE-PME</Badge>}
                </p>
                <p className="mt-1 whitespace-pre-line text-ink">{comment.body}</p>
              </li>
            );
          })}
        </ol>
      )}
      <form onSubmit={submit} className="mt-3 space-y-2">
        <label htmlFor={`comment-${actionId}`} className="sr-only">
          Votre message
        </label>
        <textarea
          id={`comment-${actionId}`}
          rows={3}
          maxLength={4000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={pmeView ? "Votre question ou votre message…" : "Votre message…"}
          className="w-full resize-y rounded-lg border border-line px-3 py-2 text-sm focus:border-brand-600 focus:outline-none"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          {!pmeView ? (
            <fieldset className="flex gap-3 text-sm">
              <legend className="sr-only">Visibilité</legend>
              <label className="flex items-center gap-1.5">
                <input type="radio" name={`visibility-${actionId}`} className="accent-brand-600" checked={visibility === "PARTAGE_PME"} onChange={() => setVisibility("PARTAGE_PME")} />
                Partagé avec la PME
              </label>
              <label className="flex items-center gap-1.5">
                <input type="radio" name={`visibility-${actionId}`} className="accent-brand-600" checked={visibility === "INTERNE_GUDE"} onChange={() => setVisibility("INTERNE_GUDE")} />
                Interne GUDE-PME
              </label>
            </fieldset>
          ) : (
            <span className="text-xs text-muted">Votre conseiller est prévenu de votre message.</span>
          )}
          <Button type="submit" disabled={!body.trim()} loading={send.isPending}>
            Envoyer
          </Button>
        </div>
        {send.error && <Alert>{errorMessage(send.error)}</Alert>}
      </form>
    </Card>
  );
}
