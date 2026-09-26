"use client";

/**
 * Éditeur sans code d'un brouillon de référentiel (Document 10, V1) : état de publication recalculé à chaque
 * modification, équilibre des poids en direct (piliers → dimensions → critères), fiches critère et question.
 * Chaque enregistrement est immédiat et tracé ; la publication reste bloquée tant qu'une anomalie subsiste.
 */
import { useState } from "react";

import { Alert, Badge, Button, Card, cx, LoadingBlock, SelectInput, TextInput } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import {
  AUDIENCES,
  type EditorCriterion,
  type EditorDimension,
  type EditorQuestion,
  type EditorTree,
  fieldErrors,
  points,
  QUESTION_TYPES,
  useEditorMutation,
  useFrameworkEditor,
} from "@/lib/frameworkEditor";
import { LENS_LABELS } from "@/lib/scoring";

import { CriterionForm } from "./CriterionForm";
import { QuestionForm } from "./QuestionForm";

export function FrameworkEditor({ versionId, onDeleted }: { versionId: string; onDeleted: () => void }) {
  const editor = useFrameworkEditor(versionId);
  const [open, setOpen] = useState<string | null>(null);
  const [addingDimension, setAddingDimension] = useState(false);
  if (editor.isLoading) return <LoadingBlock />;
  if (editor.error) return <Alert>{errorMessage(editor.error)}</Alert>;
  const tree = editor.data!;

  return (
    <div className="space-y-4">
      <PublicationStatus tree={tree} onDeleted={onDeleted} />
      <Pillars tree={tree} />
      {tree.dimensions.map((dimension) => (
        <DimensionCard
          key={dimension.id}
          tree={tree}
          dimension={dimension}
          open={open === dimension.code}
          onToggle={() => setOpen(open === dimension.code ? null : dimension.code)}
        />
      ))}
      {addingDimension ? (
        <Card title="Nouvelle dimension">
          <DimensionForm tree={tree} dimension={null} onDone={() => setAddingDimension(false)} />
        </Card>
      ) : (
        <Button variant="secondary" onClick={() => setAddingDimension(true)}>
          + Nouvelle dimension
        </Button>
      )}
    </div>
  );
}

// --- État de publication -------------------------------------------------------------------------------------

function PublicationStatus({ tree, onDeleted }: { tree: EditorTree; onDeleted: () => void }) {
  const [notes, setNotes] = useState(tree.notes);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const saveNotes = useEditorMutation(tree.id, () =>
    unwrap(api.PATCH("/api/v1/framework-versions/{version_id}/editor", { params: { path: { version_id: tree.id } }, body: { notes } })),
  );
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const remove = async () => {
    setDeleting(true);
    try {
      await unwrap(api.DELETE("/api/v1/framework-versions/{version_id}/editor", { params: { path: { version_id: tree.id } } }));
      onDeleted();
    } catch (err) {
      setDeleteError(errorMessage(err));
      setDeleting(false);
    }
  };
  const { errors, warnings } = tree.issues;

  return (
    <Card title={`Brouillon v${tree.version}`} action={errors.length ? <Badge tone="danger">{errors.length} anomalie(s)</Badge> : <Badge tone="brand">Prêt à publier</Badge>}>
      <div className="space-y-3" data-testid="publication-status">
        {errors.length > 0 ? (
          <Alert title="À corriger avant publication">
            <ul className="list-disc pl-4">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </Alert>
        ) : (
          <Alert tone="success">Pondérations équilibrées et contrôles satisfaits : ce brouillon peut être publié.</Alert>
        )}
        {warnings.length > 0 && (
          <Alert tone="warning" title="Points d'attention">
            <ul className="list-disc pl-4">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </Alert>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-0 flex-1">
            <TextInput label="Notes de version (ce qui change et pourquoi)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <Button variant="secondary" disabled={notes === tree.notes} loading={saveNotes.isPending} onClick={() => saveNotes.mutate(undefined)}>
            Enregistrer les notes
          </Button>
        </div>
        <p className="text-xs text-muted">
          Chaque modification est enregistrée immédiatement dans ce brouillon et tracée au journal d'audit. Les diagnostics en cours gardent leur
          version ; la version publiée s'applique aux nouveaux diagnostics.
        </p>
        <div className="border-t border-line pt-3">
          {confirmDelete ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              Supprimer définitivement ce brouillon ?
              <Button variant="ghost" loading={deleting} onClick={remove} className="text-red-700">
                Oui, supprimer
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                Non
              </Button>
            </div>
          ) : (
            <button className="text-xs text-red-700 hover:underline" onClick={() => setConfirmDelete(true)}>
              Supprimer ce brouillon
            </button>
          )}
          {deleteError && <Alert>{deleteError}</Alert>}
        </div>
      </div>
    </Card>
  );
}

// --- Pondérations ---------------------------------------------------------------------------------------------

function Balance({ actual, expected, label }: { actual: string; expected: string; label: string }) {
  const ok = Number(actual) === Number(expected);
  return (
    <span className={cx("whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs tabular-nums", ok ? "bg-brand-50 text-brand-800" : "bg-red-50 text-red-800")} title={label}>
      {ok ? "✓" : "⚠"} {points(actual)} / {points(expected)}
    </span>
  );
}

/** Champ de poids enregistré à la sortie du champ (ou Entrée) ; permet de rééquilibrer rapidement. */
function WeightInput({ value, label, onCommit, pending }: { value: string; label: string; onCommit: (weight: string) => void; pending?: boolean }) {
  const [draft, setDraft] = useState(points(value));
  const [shown, setShown] = useState(value);
  if (shown !== value) {
    setShown(value);
    setDraft(points(value));
  }
  const commit = () => {
    if (draft !== "" && Number(draft) !== Number(value)) onCommit(draft);
  };
  return (
    <input
      type="number"
      min={0}
      max={100}
      step="0.01"
      aria-label={label}
      className={cx("w-20 rounded-md border border-line px-2 py-1 text-right text-sm tabular-nums", pending && "opacity-60")}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
      }}
    />
  );
}

function Pillars({ tree }: { tree: EditorTree }) {
  const update = useEditorMutation(tree.id, ({ id, weight }: { id: string; weight: string }) =>
    unwrap(api.PATCH("/api/v1/framework-versions/{version_id}/pillars/{item_id}", { params: { path: { version_id: tree.id, item_id: id } }, body: { weight } })),
  );
  const balance = tree.issues.balance;
  return (
    <Card title="Piliers" action={<Balance actual={balance.pillars_total} expected="100" label="Somme des piliers" />}>
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="py-1.5 pr-3">Pilier</th>
            <th className="py-1.5 pr-3 text-right">Poids</th>
            <th className="py-1.5">Somme des dimensions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {tree.pillars.map((pillar) => {
            const b = balance.pillars.find((p) => p.code === pillar.code);
            return (
              <tr key={pillar.id}>
                <td className="py-2 pr-3">
                  <span className="font-mono text-xs text-muted">{pillar.code}</span> {pillar.name}
                </td>
                <td className="py-2 pr-3 text-right">
                  <WeightInput value={pillar.weight} label={`Poids du pilier ${pillar.code}`} onCommit={(weight) => update.mutate({ id: pillar.id, weight })} />
                </td>
                <td className="py-2">{b && <Balance actual={b.actual} expected={b.expected} label="Dimensions / poids du pilier" />}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {update.error && <Alert>{Object.values(fieldErrors(update.error))[0] ?? errorMessage(update.error)}</Alert>}
    </Card>
  );
}

// --- Dimensions -----------------------------------------------------------------------------------------------

function DimensionCard({ tree, dimension, open, onToggle }: { tree: EditorTree; dimension: EditorDimension; open: boolean; onToggle: () => void }) {
  const balance = tree.issues.balance.dimensions.find((d) => d.code === dimension.code);
  const [editing, setEditing] = useState(false);
  const [criterionForm, setCriterionForm] = useState<EditorCriterion | "new" | null>(null);
  const updateWeight = useEditorMutation(tree.id, ({ id, weight }: { id: string; weight: string }) =>
    unwrap(api.PATCH("/api/v1/framework-versions/{version_id}/criteria/{item_id}", { params: { path: { version_id: tree.id, item_id: id } }, body: { weight } })),
  );
  const updateDimensionWeight = useEditorMutation(tree.id, (weight: string) =>
    unwrap(
      api.PATCH("/api/v1/framework-versions/{version_id}/dimensions/{item_id}", {
        params: { path: { version_id: tree.id, item_id: dimension.id } },
        body: { weight },
      }),
    ),
  );

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button className="min-w-0 text-left" onClick={onToggle} aria-expanded={open}>
          <span className="font-mono text-xs text-muted">{dimension.code}</span> <span className="font-medium">{dimension.name}</span>
          <span className="ml-2 text-xs text-muted">
            pilier {dimension.pillar} · {dimension.criteria.length} critères {open ? "▲" : "▼"}
          </span>
        </button>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-xs text-muted">Poids</span>
          <WeightInput
            value={dimension.weight}
            label={`Poids de la dimension ${dimension.code}`}
            onCommit={(weight) => updateDimensionWeight.mutate(weight)}
            pending={updateDimensionWeight.isPending}
          />
          {balance && <Balance actual={balance.actual} expected={balance.expected} label="Critères du tronc commun / attendu" />}
          {balance?.modules.map((m) => (
            <span key={m.sector} className="text-xs text-muted">
              module {m.sector} <Balance actual={m.actual} expected={m.expected} label={`Module ${m.sector}`} />
            </span>
          ))}
        </div>
      </div>
      {(updateWeight.error || updateDimensionWeight.error) && (
        <div className="mt-2">
          <Alert>{errorMessage(updateWeight.error ?? updateDimensionWeight.error)}</Alert>
        </div>
      )}

      {open && (
        <div className="mt-4 space-y-4">
          {editing ? (
            <DimensionForm tree={tree} dimension={dimension} onDone={() => setEditing(false)} />
          ) : (
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm text-muted">{dimension.description || "Aucune description."}</p>
              <button className="text-xs text-brand-700 hover:underline" onClick={() => setEditing(true)}>
                Modifier la dimension
              </button>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm" aria-label={`Critères de ${dimension.code}`}>
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pr-3">Critère</th>
                  <th className="py-2 pr-3">Lentille</th>
                  <th className="py-2 pr-3 text-right">Poids</th>
                  <th className="py-2 pr-3">Questions</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line align-top">
                {dimension.criteria.map((criterion) => (
                  <CriterionRow
                    key={criterion.id}
                    tree={tree}
                    criterion={criterion}
                    onEdit={() => setCriterionForm(criterion)}
                    onWeight={(weight) => updateWeight.mutate({ id: criterion.id, weight })}
                    editing={criterionForm !== "new" && criterionForm?.id === criterion.id}
                    onDone={() => setCriterionForm(null)}
                    dimensionCode={dimension.code}
                  />
                ))}
              </tbody>
            </table>
          </div>
          {criterionForm === "new" ? (
            <CriterionForm versionId={tree.id} dimension={dimension.code} criterion={null} onDone={() => setCriterionForm(null)} />
          ) : (
            <Button variant="secondary" onClick={() => setCriterionForm("new")}>
              + Nouveau critère dans {dimension.code}
            </Button>
          )}

          {dimension.questions.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Questions de profil et données de la dimension</p>
              <QuestionList tree={tree} questions={dimension.questions} parent={{ dimension: dimension.code }} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function DimensionForm({ tree, dimension, onDone }: { tree: EditorTree; dimension: EditorDimension | null; onDone: () => void }) {
  const [form, setForm] = useState({
    code: "",
    pillar: dimension?.pillar ?? tree.pillars[0]?.code ?? "",
    name: dimension?.name ?? "",
    short_name: dimension?.short_name ?? "",
    description: dimension?.description ?? "",
    weight: dimension ? points(dimension.weight) : "",
    sector_module_share: dimension ? points(dimension.sector_module_share) : "0",
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  const save = useEditorMutation(
    tree.id,
    () => {
      const body = {
        pillar: form.pillar,
        name: form.name,
        short_name: form.short_name,
        description: form.description,
        weight: form.weight,
        sector_module_share: form.sector_module_share || "0",
      };
      return dimension
        ? unwrap(api.PATCH("/api/v1/framework-versions/{version_id}/dimensions/{item_id}", { params: { path: { version_id: tree.id, item_id: dimension.id } }, body }))
        : unwrap(api.POST("/api/v1/framework-versions/{version_id}/dimensions", { params: { path: { version_id: tree.id } }, body: { ...body, code: form.code.trim().toUpperCase() } }));
    },
    onDone,
  );
  const remove = useEditorMutation(
    tree.id,
    () => unwrap(api.DELETE("/api/v1/framework-versions/{version_id}/dimensions/{item_id}", { params: { path: { version_id: tree.id, item_id: dimension!.id } } })),
    onDone,
  );
  const errors = fieldErrors(save.error);

  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {!dimension && <TextInput label="Code de la dimension" value={form.code} onChange={(e) => set({ code: e.target.value.toUpperCase() })} hint="Ex. D13" error={errors.code} required />}
      <SelectInput label="Pilier" value={form.pillar} onChange={(e) => set({ pillar: e.target.value })} placeholder="—" options={tree.pillars.map((p) => ({ value: p.code, label: `${p.code} · ${p.name}` }))} error={errors.pillar} />
      <TextInput label="Libellé" value={form.name} onChange={(e) => set({ name: e.target.value })} error={errors.name} required />
      <TextInput label="Nom court (graphiques)" value={form.short_name} onChange={(e) => set({ short_name: e.target.value })} maxLength={60} error={errors.short_name} />
      <TextInput label="Poids dans le pilier (points)" type="number" min={0.01} step="0.01" value={form.weight} onChange={(e) => set({ weight: e.target.value })} error={errors.weight} required />
      <TextInput
        label="Part du module sectoriel (%)"
        type="number"
        min={0}
        max={100}
        step="0.01"
        value={form.sector_module_share}
        onChange={(e) => set({ sector_module_share: e.target.value })}
        hint="0 : pas de module sectoriel."
        error={errors.sector_module_share}
      />
      <div className="sm:col-span-2">
        <TextInput label="Description" value={form.description} onChange={(e) => set({ description: e.target.value })} error={errors.description} />
      </div>
      {(save.error || remove.error) && Object.keys(errors).length === 0 && (
        <div className="sm:col-span-2">
          <Alert>{errorMessage(save.error ?? remove.error)}</Alert>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {dimension ? "Enregistrer la dimension" : "Ajouter la dimension"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Annuler
        </Button>
        {dimension &&
          (confirmDelete ? (
            <span className="text-sm">
              Supprimer {dimension.code} ?{" "}
              <button type="button" className="text-red-700 hover:underline" onClick={() => remove.mutate(undefined)}>
                Oui
              </button>{" "}
              <button type="button" className="hover:underline" onClick={() => setConfirmDelete(false)}>
                Non
              </button>
            </span>
          ) : (
            <button type="button" className="ml-auto text-xs text-red-700 hover:underline" onClick={() => setConfirmDelete(true)}>
              Supprimer la dimension (vide)
            </button>
          ))}
      </div>
    </form>
  );
}

// --- Critères et questions ------------------------------------------------------------------------------------

function CriterionRow({
  tree,
  criterion,
  editing,
  onEdit,
  onDone,
  onWeight,
  dimensionCode,
}: {
  tree: EditorTree;
  criterion: EditorCriterion;
  editing: boolean;
  onEdit: () => void;
  onDone: () => void;
  onWeight: (weight: string) => void;
  dimensionCode: string;
}) {
  const [showQuestions, setShowQuestions] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const remove = useEditorMutation(tree.id, () =>
    unwrap(api.DELETE("/api/v1/framework-versions/{version_id}/criteria/{item_id}", { params: { path: { version_id: tree.id, item_id: criterion.id } } })),
  );
  return (
    <>
      <tr>
        <td className="py-2 pr-3">
          <span className="font-mono text-xs text-muted">{criterion.code}</span> {criterion.name}
          <div className="mt-1 flex flex-wrap gap-1">
            {criterion.is_critical && <Badge tone="warning">Critique</Badge>}
            {criterion.sector_module && <Badge tone="info">Module {criterion.sector_module}</Badge>}
            {Boolean(criterion.applicability) && <Badge tone="muted">Conditionnel</Badge>}
            {criterion.metrics.length > 0 && <Badge tone="muted">Indicateur calculé</Badge>}
          </div>
        </td>
        <td className="py-2 pr-3 text-muted">{LENS_LABELS[criterion.lens]}</td>
        <td className="py-2 pr-3 text-right">
          <WeightInput value={criterion.weight} label={`Poids de ${criterion.code}`} onCommit={onWeight} />
        </td>
        <td className="py-2 pr-3">
          <button className="whitespace-nowrap text-xs text-brand-700 hover:underline" onClick={() => setShowQuestions(!showQuestions)}>
            {criterion.questions.length} question(s) {showQuestions ? "▲" : "▼"}
          </button>
        </td>
        <td className="whitespace-nowrap py-2 text-right text-xs">
          <button className="text-brand-700 hover:underline" onClick={onEdit} aria-label={`Modifier ${criterion.code}`}>
            Modifier
          </button>
          {confirmDelete ? (
            <span className="ml-2">
              Supprimer ?{" "}
              <button className="text-red-700 hover:underline" onClick={() => remove.mutate(undefined)}>
                Oui
              </button>{" "}
              <button className="hover:underline" onClick={() => setConfirmDelete(false)}>
                Non
              </button>
            </span>
          ) : (
            <button className="ml-2 text-red-700 hover:underline" onClick={() => setConfirmDelete(true)} aria-label={`Supprimer ${criterion.code}`}>
              Supprimer
            </button>
          )}
        </td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={5} className="py-3">
            <CriterionForm versionId={tree.id} dimension={dimensionCode} criterion={criterion} onDone={onDone} />
          </td>
        </tr>
      )}
      {showQuestions && (
        <tr>
          <td colSpan={5} className="bg-gray-50/50 px-3 py-3">
            <QuestionList
              tree={tree}
              questions={criterion.questions}
              parent={{ criterion: criterion.code }}
              defaultOptions={criterion.rubric.map((label, level) => ({ label, level }))}
            />
          </td>
        </tr>
      )}
      {remove.error && (
        <tr>
          <td colSpan={5}>
            <Alert>{errorMessage(remove.error)}</Alert>
          </td>
        </tr>
      )}
    </>
  );
}

function QuestionList({
  tree,
  questions,
  parent,
  defaultOptions,
}: {
  tree: EditorTree;
  questions: EditorQuestion[];
  parent: { criterion?: string; dimension?: string };
  defaultOptions?: { label: string; level: number }[];
}) {
  const [editing, setEditing] = useState<EditorQuestion | "new" | null>(null);
  const remove = useEditorMutation(tree.id, (id: string) =>
    unwrap(api.DELETE("/api/v1/framework-versions/{version_id}/questions/{item_id}", { params: { path: { version_id: tree.id, item_id: id } } })),
  );
  return (
    <div className="space-y-2">
      <ul className="space-y-1.5">
        {questions.map((question) =>
          editing !== "new" && editing?.id === question.id ? (
            <li key={question.id}>
              <QuestionForm versionId={tree.id} question={question} parent={parent} onDone={() => setEditing(null)} />
            </li>
          ) : (
            <li key={question.id} className="flex flex-wrap items-start justify-between gap-2 text-sm">
              <span className="min-w-0">
                <span className="font-mono text-xs text-muted">{question.code}</span> {question.text}
                <span className="block text-xs text-muted">
                  {QUESTION_TYPES[question.type]} · {AUDIENCES[question.target_audience]}
                  {!question.is_required && " · facultative"}
                  {question.feeds && ` · alimente ${question.feeds}`}
                  {question.visibility ? " · affichage conditionnel" : ""}
                </span>
              </span>
              <span className="whitespace-nowrap text-xs">
                <button className="text-brand-700 hover:underline" onClick={() => setEditing(question)} aria-label={`Modifier la question ${question.code}`}>
                  Modifier
                </button>
                {!question.feeds && (
                  <button className="ml-2 text-red-700 hover:underline" onClick={() => remove.mutate(question.id)} aria-label={`Supprimer la question ${question.code}`}>
                    Supprimer
                  </button>
                )}
              </span>
            </li>
          ),
        )}
      </ul>
      {remove.error && <Alert>{errorMessage(remove.error)}</Alert>}
      {editing === "new" ? (
        <QuestionForm versionId={tree.id} question={null} parent={parent} defaultOptions={defaultOptions} onDone={() => setEditing(null)} />
      ) : (
        <button className="text-xs text-brand-700 hover:underline" onClick={() => setEditing("new")}>
          + Ajouter une question
        </button>
      )}
    </div>
  );
}
