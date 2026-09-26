"use client";

/**
 * Types de documents (Document 10, V1) : ce que les PME déposent, avec validité, fraîcheur et niveau de preuve.
 * Le code est fixé à la création (il est référencé par les critères, obligations et livrables) ; un type exigé par une
 * obligation active ne peut pas être désactivé.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card, LoadingBlock, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";

const PERIOD_KINDS: Record<Schemas["PeriodKindEnum"], string> = {
  AUCUNE: "Aucune (document permanent)",
  MOIS: "Mois",
  TRIMESTRE: "Trimestre",
  SEMESTRE: "Semestre",
  ANNEE: "Année",
  EXERCICE: "Exercice comptable",
};
const EVIDENCE_LEVELS = [0, 1, 2, 3, 4].map((n) => `Niveau ${n} du critère`);

type DocumentType = Schemas["DocumentTypeAdmin"];

export function DocumentTypesAdmin() {
  const types = useQuery({ queryKey: ["config-document-types"], queryFn: () => unwrap(api.GET("/api/v1/config/document-types")) });
  const [editing, setEditing] = useState<DocumentType | "new" | null>(null);
  if (types.isLoading) return <LoadingBlock />;
  if (types.error) return <Alert>{errorMessage(types.error)}</Alert>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {types.data!.length} types de documents. Un type inactif n'est plus proposé au dépôt ; les documents déjà déposés sont conservés.
        </p>
        {editing === null && <Button onClick={() => setEditing("new")}>Nouveau type de document</Button>}
      </div>
      {editing !== null && (
        <Card title={editing === "new" ? "Nouveau type de document" : `Modifier « ${editing.name} »`}>
          <DocumentTypeForm key={editing === "new" ? "new" : editing.id} initial={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        </Card>
      )}
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Catégorie</th>
                <th className="py-2 pr-4">Période · validité</th>
                <th className="py-2 pr-4">Utilisé par</th>
                <th className="py-2 pr-4">Statut</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line align-top">
              {types.data!.map((t) => (
                <tr key={t.id}>
                  <td className="py-2.5 pr-4">
                    <p className="font-medium">{t.name}</p>
                    <p className="font-mono text-xs text-muted">{t.code}</p>
                  </td>
                  <td className="py-2.5 pr-4 text-muted">{t.category_name}</td>
                  <td className="py-2.5 pr-4 text-muted">
                    {PERIOD_KINDS[t.period_kind ?? "AUCUNE"]}
                    {t.validity_days ? ` · valide ${t.validity_days} j` : ""}
                    {t.freshness_days ? ` · frais ${t.freshness_days} j` : ""}
                  </td>
                  <td className="py-2.5 pr-4 text-xs text-muted">
                    {t.usage.documents} document(s)
                    {t.usage.obligations.length > 0 && <span className="block">Obligations : {t.usage.obligations.join(", ")}</span>}
                    {t.usage.criteria.length > 0 && <span className="block">Critères : {t.usage.criteria.join(", ")}</span>}
                  </td>
                  <td className="py-2.5 pr-4">
                    {t.is_active ? <Badge tone="brand">Actif</Badge> : <Badge tone="muted">Inactif</Badge>}
                    {t.sensitive && (
                      <span className="ml-1">
                        <Badge tone="warning">Sensible</Badge>
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-right">
                    <button className="text-xs text-brand-700 hover:underline" onClick={() => setEditing(t)} aria-label={`Modifier ${t.name}`}>
                      Modifier
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function DocumentTypeForm({ initial, onDone }: { initial: DocumentType | null; onDone: () => void }) {
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ["config-document-categories"], queryFn: () => unwrap(api.GET("/api/v1/config/document-categories")) });
  const [form, setForm] = useState({
    code: initial?.code ?? "",
    name: initial?.name ?? "",
    category: initial?.category ?? "",
    description: initial?.description ?? "",
    guidance: initial?.guidance ?? "",
    period_kind: (initial?.period_kind ?? "AUCUNE") as Schemas["PeriodKindEnum"],
    validity_days: initial?.validity_days ? String(initial.validity_days) : "",
    freshness_days: initial?.freshness_days ? String(initial.freshness_days) : "",
    evidence_level: String(initial?.evidence_level ?? 3),
    sensitive: initial?.sensitive ?? false,
    order: String(initial?.order ?? 100),
    is_active: initial?.is_active ?? true,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        category: form.category,
        description: form.description,
        guidance: form.guidance,
        period_kind: form.period_kind,
        validity_days: form.validity_days ? Number(form.validity_days) : null,
        freshness_days: form.freshness_days ? Number(form.freshness_days) : null,
        evidence_level: Number(form.evidence_level),
        sensitive: form.sensitive,
        order: Number(form.order || 0),
        is_active: form.is_active,
      };
      return initial
        ? unwrap(api.PATCH("/api/v1/config/document-types/{type_id}", { params: { path: { type_id: initial.id } }, body }))
        : unwrap(api.POST("/api/v1/config/document-types", { body: { ...body, code: form.code.trim().toUpperCase() } }));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config-document-types"] });
      queryClient.invalidateQueries({ queryKey: ["document-types"] });
      onDone();
    },
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });
  const fieldError = save.error instanceof ApiError && Object.keys(save.error.fieldErrors()).length > 0;

  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {initial ? (
        <p className="text-sm sm:col-span-2">
          Code <span className="font-mono">{initial.code}</span> <span className="text-xs text-muted">(non modifiable : référencé par les critères et obligations)</span>
        </p>
      ) : (
        <TextInput
          label="Code"
          value={form.code}
          onChange={(e) => set({ code: e.target.value.toUpperCase() })}
          hint="Majuscules, chiffres, - et _ ; définitif après création."
          error={errors.code}
          required
        />
      )}
      <TextInput label="Libellé" value={form.name} onChange={(e) => set({ name: e.target.value })} error={errors.name} required />
      <SelectInput
        label="Catégorie"
        value={form.category}
        onChange={(e) => set({ category: e.target.value })}
        options={(categories.data ?? []).map((c) => ({ value: c.code, label: c.name }))}
        error={errors.category}
        required
      />
      <SelectInput
        label="Période couverte"
        value={form.period_kind}
        onChange={(e) => set({ period_kind: e.target.value as Schemas["PeriodKindEnum"] })}
        options={Object.entries(PERIOD_KINDS).map(([value, label]) => ({ value, label }))}
        error={errors.period_kind}
      />
      <TextInput
        label="Durée de validité (jours)"
        type="number"
        min={1}
        value={form.validity_days}
        onChange={(e) => set({ validity_days: e.target.value })}
        hint="Vide : pas d'expiration (ex. 90 pour une attestation fiscale)."
        error={errors.validity_days}
      />
      <TextInput
        label="Fraîcheur attendue (jours)"
        type="number"
        min={1}
        value={form.freshness_days}
        onChange={(e) => set({ freshness_days: e.target.value })}
        hint="Au-delà, le document est signalé comme ancien."
        error={errors.freshness_days}
      />
      <SelectInput
        label="Niveau prouvé par ce document"
        value={form.evidence_level}
        onChange={(e) => set({ evidence_level: e.target.value })}
        placeholder="—"
        options={EVIDENCE_LEVELS.map((label, i) => ({ value: String(i), label }))}
        error={errors.evidence_level}
      />
      <TextInput label="Ordre d'affichage" type="number" min={0} value={form.order} onChange={(e) => set({ order: e.target.value })} error={errors.order} />
      <div className="sm:col-span-2">
        <TextInput label="Description" value={form.description} onChange={(e) => set({ description: e.target.value })} error={errors.description} />
      </div>
      <div className="sm:col-span-2">
        <TextInput
          label="Consigne pour la PME"
          value={form.guidance}
          onChange={(e) => set({ guidance: e.target.value })}
          hint="Affichée au dépôt : où obtenir le document, ce qu'il doit contenir."
          error={errors.guidance}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.sensitive} onChange={(e) => set({ sensitive: e.target.checked })} />
        Données personnelles (jamais envoyé à une IA externe)
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
        Actif (proposé au dépôt)
      </label>
      {save.error && !fieldError && (
        <div className="sm:col-span-2">
          <Alert>{errorMessage(save.error)}</Alert>
        </div>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {initial ? "Enregistrer" : "Créer le type"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Annuler
        </Button>
      </div>
    </form>
  );
}
