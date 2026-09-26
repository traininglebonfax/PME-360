"use client";

/**
 * Modèles de notification (Document 7, § 8.3 ; Document 10, V1) : l'organisation adapte l'objet et le texte de
 * chaque message, en langage simple pour la PME. Variables insérables, aperçu en direct avec des valeurs d'exemple,
 * envoi d'un e-mail de test, retour au texte par défaut. Chaque modification est tracée au journal d'audit.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { Alert, Badge, Button, Card, cx, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { checkTemplate, insertVariable, renderTemplate } from "@/lib/notificationTemplates";

type Template = Schemas["NotificationTemplateAdmin"];

export default function NotificationTemplatesPage() {
  const templates = useQuery({ queryKey: ["notification-templates"], queryFn: () => unwrap(api.GET("/api/v1/config/notification-templates")) });
  const [selected, setSelected] = useState<string | null>(null);
  const current = templates.data?.find((t) => t.event_code === selected) ?? templates.data?.[0];

  return (
    <>
      <PageHeader
        title="Modèles de notification"
        subtitle="Objet et texte des messages envoyés dans l'application et par e-mail. Écrivez simplement : la plupart sont lus par des dirigeants de PME."
      />
      {templates.isLoading ? (
        <LoadingBlock />
      ) : templates.error ? (
        <Alert>{errorMessage(templates.error)}</Alert>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
          <Card>
            <ul className="-my-1 divide-y divide-line" aria-label="Événements">
              {templates.data!.map((t) => (
                <li key={t.event_code}>
                  <button
                    onClick={() => setSelected(t.event_code)}
                    aria-current={current?.event_code === t.event_code}
                    className={cx(
                      "w-full rounded-md px-2 py-2 text-left text-sm",
                      current?.event_code === t.event_code ? "bg-brand-50 font-medium text-brand-800" : "hover:bg-gray-50",
                    )}
                  >
                    {t.label}
                    <span className="block text-xs font-normal text-muted">
                      {t.audience}
                      {!t.is_default && " · personnalisé"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {current && <TemplateEditor key={current.event_code} template={current} />}
        </div>
      )}
    </>
  );
}

function TemplateEditor({ template }: { template: Template }) {
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const subjectRef = useRef<HTMLInputElement>(null);
  const lastFocus = useRef<"subject" | "body">("body");

  const names = template.variables.map((v) => v.name);
  const examples = useMemo(() => Object.fromEntries(template.variables.map((v) => [v.name, v.example])), [template.variables]);
  const subjectErrors = checkTemplate(subject, names);
  const bodyErrors = checkTemplate(body, names);
  const dirty = subject !== template.subject || body !== template.body;
  const invalid = subjectErrors.length > 0 || bodyErrors.length > 0 || !subject.trim() || !body.trim();

  const onSaved = (data: Template) => {
    queryClient.setQueryData<Template[]>(["notification-templates"], (items) => items?.map((t) => (t.event_code === data.event_code ? data : t)));
  };
  const params = { params: { path: { event_code: template.event_code } } };
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/api/v1/config/notification-templates/{event_code}", { ...params, body: { subject, body } })),
    onSuccess: onSaved,
    onError: (err) => setServerErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });
  const reset = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/config/notification-templates/{event_code}/reset", params)),
    onSuccess: (data) => {
      onSaved(data);
      setSubject(data.subject);
      setBody(data.body);
      save.reset();
    },
  });
  const test = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/config/notification-templates/{event_code}/test", { ...params, body: { subject, body } })),
  });

  const insert = (name: string) => {
    const target = lastFocus.current === "subject" ? subjectRef.current : bodyRef.current;
    const text = lastFocus.current === "subject" ? subject : body;
    const start = target?.selectionStart ?? text.length;
    const end = target?.selectionEnd ?? text.length;
    const result = insertVariable(text, name, start, end);
    if (lastFocus.current === "subject") setSubject(result.text);
    else setBody(result.text);
    requestAnimationFrame(() => {
      target?.focus();
      target?.setSelectionRange(result.caret, result.caret);
    });
  };

  const previewSubject = renderTemplate(subject, examples);
  const previewBody = renderTemplate(body, examples).trim();

  return (
    <div className="space-y-6">
      <Card
        title={template.label}
        action={
          <span className="flex gap-1">
            {template.mandatory && <Badge tone="warning">Toujours envoyé</Badge>}
            {template.is_default ? <Badge tone="muted">Texte par défaut</Badge> : <Badge tone="brand">Personnalisé</Badge>}
          </span>
        }
      >
        <p className="mb-4 text-sm text-muted">
          Destinataires : {template.audience}.{!template.is_default && template.updated_at && ` Modifié le ${formatDateTime(template.updated_at)}.`}
        </p>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            setServerErrors({});
            save.mutate();
          }}
        >
          <TextInput
            ref={subjectRef}
            label="Objet"
            value={subject}
            maxLength={200}
            onFocus={() => (lastFocus.current = "subject")}
            onChange={(e) => setSubject(e.target.value)}
            error={subjectErrors.join(" ") || serverErrors.subject}
            required
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="template-body" className="text-sm font-medium text-ink">
              Message<span className="text-red-600"> *</span>
            </label>
            <textarea
              id="template-body"
              ref={bodyRef}
              rows={5}
              maxLength={2000}
              value={body}
              onFocus={() => (lastFocus.current = "body")}
              onChange={(e) => setBody(e.target.value)}
              aria-invalid={bodyErrors.length > 0}
              className={cx(
                "w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-ink focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-100",
                bodyErrors.length || serverErrors.body ? "border-red-400" : "border-line",
              )}
            />
            {(bodyErrors.length > 0 || serverErrors.body) && (
              <p className="text-xs text-red-700" role="alert">
                {bodyErrors.join(" ") || serverErrors.body}
              </p>
            )}
          </div>
          <div>
            <p className="mb-1.5 text-xs text-muted">Variables : cliquez pour insérer à l'emplacement du curseur.</p>
            <div className="flex flex-wrap gap-2" aria-label="Variables disponibles">
              {template.variables.map((v) => (
                <button
                  key={v.name}
                  type="button"
                  onClick={() => insert(v.name)}
                  title={v.example ? `Exemple : ${v.example}` : undefined}
                  className="rounded-md border border-line px-2 py-1 text-xs hover:border-brand-600 hover:bg-brand-50"
                >
                  <span className="font-mono">{`{${v.name}}`}</span> <span className="text-muted">{v.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={save.isPending} disabled={!dirty || invalid}>
              Enregistrer
            </Button>
            <Button type="button" variant="secondary" loading={test.isPending} disabled={invalid} onClick={() => test.mutate()}>
              M'envoyer un e-mail de test
            </Button>
            {!template.is_default && (
              <Button type="button" variant="ghost" loading={reset.isPending} onClick={() => reset.mutate()}>
                Revenir au texte par défaut
              </Button>
            )}
            {dirty && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setSubject(template.subject);
                  setBody(template.body);
                }}
              >
                Annuler les modifications
              </Button>
            )}
          </div>
          {save.isSuccess && !dirty && <Alert tone="success">Modèle enregistré : il s'applique aux prochains messages.</Alert>}
          {test.data && <Alert tone="success">E-mail de test envoyé à {test.data.email}.</Alert>}
          {[save.error, reset.error, test.error]
            .filter((err) => err && !(err instanceof ApiError && Object.keys(err.fieldErrors()).length))
            .map((err, i) => (
              <Alert key={i}>{errorMessage(err)}</Alert>
            ))}
        </form>
      </Card>

      <Card title="Aperçu avec des valeurs d'exemple">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Dans l'application</p>
            <div className="rounded-lg border border-line p-3" data-testid="preview-inapp">
              <p className="text-sm font-medium">{previewSubject}</p>
              <p className="mt-1 whitespace-pre-line text-sm text-muted">{previewBody}</p>
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">E-mail</p>
            <div className="rounded-lg border border-line p-3 text-sm">
              <p className="border-b border-line pb-2">
                <span className="text-muted">Objet :</span> {previewSubject}
              </p>
              <p className="mt-2 whitespace-pre-line">{`Bonjour Aya Koffi,\n\n${previewBody}\n\n[lien vers PME360]\n\nL'équipe PME360`}</p>
            </div>
          </div>
        </div>
        {!template.is_default && (
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer text-muted">Voir le texte par défaut</summary>
            <p className="mt-2 font-medium">{template.default_subject}</p>
            <p className="text-muted">{template.default_body}</p>
          </details>
        )}
      </Card>
    </div>
  );
}
