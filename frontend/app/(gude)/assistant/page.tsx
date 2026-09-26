"use client";

/**
 * Copilot (Document 4, § 9) : questions en langage naturel sur une PME ou sur le portefeuille. Les réponses
 * s'appuient uniquement sur les données du périmètre de l'utilisateur, citent leurs sources et leurs limites.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useRef, useState } from "react";

import { Alert, Badge, Button, cx, EmptyState, LoadingBlock, PageHeader, Spinner } from "@/components/ui";
import { type AskMessage, askQuestion, type AskSource } from "@/lib/ai";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatRelative } from "@/lib/format";

type Source = AskSource;
type Turn = { id: string; role: "USER" | "ASSISTANT"; content: string; sources: Source[]; confidence: string | null; limits: string[]; analysis?: string | null };

const CONFIDENCE: Record<string, { label: string; tone: "brand" | "warning" | "danger" }> = {
  ELEVEE: { label: "Confiance élevée", tone: "brand" },
  MOYENNE: { label: "Confiance moyenne", tone: "warning" },
  FAIBLE: { label: "Confiance faible", tone: "danger" },
};

const PME_QUESTIONS = [
  "Quels sont les principaux problèmes de cette PME et pourquoi ?",
  "Quels documents manquent ou sont expirés ?",
  "Quelles échéances arrivent dans les 30 prochains jours ?",
  "Comment a-t-elle évolué depuis le dernier diagnostic ?",
  "Que disent ses ratios financiers ?",
];
const PORTFOLIO_QUESTIONS = [
  "Quelles PME nécessitent une intervention urgente ?",
  "Quels sont les problèmes les plus fréquents du portefeuille ?",
  "Quelles PME progressent ou stagnent ?",
];

function toTurn(message: Schemas["Message"]): Turn {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    sources: (message.sources as Source[]) ?? [],
    confidence: message.confidence || null,
    limits: (message.limits as string[]) ?? [],
    analysis: message.analysis,
  };
}

export default function AssistantPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <Assistant />
    </Suspense>
  );
}

function Assistant() {
  const params = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const pmeId = params.get("pme");
  const selectedId = params.get("conversation");

  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: () => unwrap(api.GET("/api/v1/ai/conversations")),
  });
  const pme = useQuery({
    queryKey: ["pme", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{id}", { params: { path: { id: pmeId! } } })),
    enabled: Boolean(pmeId) && !selectedId,
  });
  const detail = useQuery({
    queryKey: ["conversation", selectedId],
    queryFn: () => unwrap(api.GET("/api/v1/ai/conversations/{conversation_id}", { params: { path: { conversation_id: selectedId! } } })),
    enabled: Boolean(selectedId),
  });

  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState<{ status: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Synchronise l'affichage sur la conversation chargée (ou la vide pour une nouvelle).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTurns(detail.data ? detail.data.messages.map(toTurn) : []);
  }, [detail.data, selectedId]);
  useEffect(() => {
    // Bloc explicite : scrollIntoView renvoie une promesse dans les navigateurs récents (un effet ne renvoie rien).
    void bottom.current?.scrollIntoView({ block: "end" });
  }, [turns, pending]);

  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/ai/conversations", { body: { pme_id: pmeId, title: "" } })),
  });

  const context = selectedId ? detail.data?.pme_name || "Mon portefeuille" : pmeId ? pme.data?.legal_name : "Mon portefeuille";
  const onPme = selectedId ? Boolean(detail.data?.pme) : Boolean(pmeId);

  async function send(text: string) {
    const value = text.trim();
    if (!value || pending) return;
    setError(null);
    setQuestion("");
    setTurns((current) => [...current, { id: `q-${Date.now()}`, role: "USER", content: value, sources: [], confidence: null, limits: [] }]);
    setPending({ status: "Réflexion…", text: "" });
    try {
      let conversationId = selectedId;
      if (!conversationId) {
        const created = await create.mutateAsync();
        conversationId = created.id;
      }
      let answered: AskMessage | null = null;
      await askQuestion(conversationId, value, (event) => {
        if (event.type === "status") setPending((p) => ({ status: event.text, text: p?.text ?? "" }));
        else if (event.type === "delta") setPending((p) => ({ status: "", text: (p?.text ?? "") + event.text }));
        else if (event.type === "done") answered = event.message;
        else if (event.type === "error") setError(event.text);
      });
      const message = answered as AskMessage | null;
      if (message)
        setTurns((current) => [
          ...current,
          {
            id: message.id,
            role: "ASSISTANT",
            content: message.content,
            sources: message.sources,
            confidence: message.confidence,
            limits: message.limits,
            analysis: message.analysis_id,
          },
        ]);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (conversationId !== selectedId) {
        queryClient.setQueryData(["conversation", conversationId], undefined);
        router.replace(`/assistant?conversation=${conversationId}`);
      } else {
        queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send(question);
  }

  const suggestions = onPme ? PME_QUESTIONS : PORTFOLIO_QUESTIONS;

  return (
    <>
      <PageHeader
        title="Copilot"
        subtitle="Posez vos questions en langage simple. Les réponses citent leurs sources ; elles ne remplacent pas votre jugement."
      />
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <aside className="space-y-2">
          <Link
            href="/assistant"
            className="block rounded-lg border border-line bg-white px-3 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50"
          >
            + Question sur le portefeuille
          </Link>
          {conversations.isLoading ? (
            <LoadingBlock />
          ) : (
            <ul className="space-y-1" aria-label="Conversations">
              {conversations.data?.map((conversation) => (
                <li key={conversation.id}>
                  <Link
                    href={`/assistant?conversation=${conversation.id}`}
                    className={cx(
                      "block rounded-lg px-3 py-2 text-sm hover:bg-gray-50",
                      conversation.id === selectedId ? "bg-brand-50 font-medium text-brand-800" : "text-ink",
                    )}
                  >
                    <span className="block truncate">{conversation.title}</span>
                    <span className="text-xs text-muted">{formatRelative(conversation.updated_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="flex min-h-[60vh] flex-col rounded-xl border border-line bg-white">
          <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <p className="text-sm">
              <span className="text-muted">Contexte : </span>
              <span className="font-medium">{context ?? "…"}</span>
            </p>
            {onPme && (detail.data?.pme || pmeId) && (
              <Link href={`/pme/${detail.data?.pme ?? pmeId}`} className="text-sm text-brand-700 hover:underline">
                Fiche PME
              </Link>
            )}
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
            {detail.isLoading && <LoadingBlock />}
            {detail.error && <Alert>{errorMessage(detail.error)}</Alert>}
            {turns.length === 0 && !pending && !detail.isLoading && (
              <EmptyState title="Que souhaitez-vous savoir ?">
                <div className="mt-3 flex flex-wrap justify-center gap-2">
                  {suggestions.map((item) => (
                    <button
                      key={item}
                      onClick={() => void send(item)}
                      className="rounded-full border border-line bg-white px-3 py-1.5 text-sm text-ink hover:border-brand-600 hover:text-brand-800"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </EmptyState>
            )}
            {turns.map((turn) => (
              <TurnView key={turn.id} turn={turn} />
            ))}
            {pending && (
              <div className="max-w-3xl rounded-xl bg-gray-50 px-4 py-3 text-sm">
                {pending.text ? (
                  <p className="whitespace-pre-line">{pending.text}</p>
                ) : (
                  <p className="flex items-center gap-2 text-muted">
                    <Spinner className="h-4 w-4" /> {pending.status}
                  </p>
                )}
              </div>
            )}
            {error && <Alert>{error}</Alert>}
            <div ref={bottom} />
          </div>

          <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
            <label htmlFor="question" className="sr-only">
              Votre question
            </label>
            <textarea
              id="question"
              rows={2}
              value={question}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(question);
                }
              }}
              placeholder={onPme ? "Ex. : pourquoi son score est-il faible ?" : "Ex. : quelles PME sont prioritaires ?"}
              className="flex-1 resize-none rounded-lg border border-line px-3 py-2 text-sm focus:border-brand-600 focus:outline-none"
            />
            <Button type="submit" disabled={!question.trim() || Boolean(pending)}>
              Envoyer
            </Button>
          </form>
        </section>
      </div>
    </>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === "USER")
    return (
      <div className="ml-auto max-w-2xl rounded-xl bg-brand-600 px-4 py-2.5 text-sm text-white">
        <p className="whitespace-pre-line">{turn.content}</p>
      </div>
    );
  const confidence = turn.confidence ? CONFIDENCE[turn.confidence] : null;
  return (
    <article className="max-w-3xl rounded-xl bg-gray-50 px-4 py-3 text-sm" data-testid="assistant-answer">
      <p className="whitespace-pre-line text-ink">{turn.content}</p>
      <div className="mt-3 space-y-2 border-t border-line pt-2 text-xs text-muted">
        <div className="flex flex-wrap items-center gap-2">
          {confidence && <Badge tone={confidence.tone}>{confidence.label}</Badge>}
          {turn.analysis && (
            <Link href={`/ia/analyses/${turn.analysis}`} className="text-brand-700 hover:underline">
              Traçabilité
            </Link>
          )}
        </div>
        {turn.sources.length > 0 && (
          <div>
            <p className="font-medium text-ink">Sources</p>
            <ul className="list-inside list-disc">
              {turn.sources.map((source, index) => (
                <li key={index}>
                  {source.label}
                  {source.detail && <span> — {source.detail}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {turn.limits.length > 0 && (
          <div>
            <p className="font-medium text-ink">Limites</p>
            <ul className="list-inside list-disc">
              {turn.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
}
