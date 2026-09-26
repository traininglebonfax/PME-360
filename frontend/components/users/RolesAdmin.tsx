"use client";

/**
 * Rôles (Document 1, § 6 ; V1) : rôles système en lecture seule, rôles personnalisés composés à partir des
 * permissions atomiques. On ne peut accorder que ce que l'on détient ; un rôle attribué ne se supprime pas.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card, LoadingBlock, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { SCOPE_LABELS } from "@/lib/labels";

type Role = Schemas["RoleAdmin"];
type Draft = { id: string | null; code: string; label: string; default_scope: "ORG" | "PROGRAMME" | "PORTEFEUILLE"; permissions: string[] };
const STAFF_SCOPES = ["ORG", "PROGRAMME", "PORTEFEUILLE"] as const;

export function RolesAdmin() {
  const queryClient = useQueryClient();
  const data = useQuery({ queryKey: ["config-roles"], queryFn: () => unwrap(api.GET("/api/v1/config/roles")) });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["config-roles"] });
    queryClient.invalidateQueries({ queryKey: ["roles"] });
  };
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/config/roles/{role_id}", { params: { path: { role_id: id } } })),
    onSuccess: () => {
      setConfirm(null);
      refresh();
    },
  });
  if (data.isLoading) return <LoadingBlock />;
  if (data.error) return <Alert>{errorMessage(data.error)}</Alert>;
  const { roles, permission_groups: groups, grantable } = data.data!;
  const labels = Object.fromEntries(groups.flatMap((g) => g.permissions.map((p) => [p.code, p.label])));
  const custom = roles.filter((r) => !r.is_system);
  const system = roles.filter((r) => r.is_system && !r.is_pme_role);

  const startFrom = (role: Role | null) =>
    setDraft({
      id: null,
      code: "",
      label: role ? `${role.label} (adapté)` : "",
      default_scope: role && role.default_scope !== "PME" ? role.default_scope : "PORTEFEUILLE",
      permissions: role ? role.permissions.filter((p) => grantable.includes(p)) : ["pme.view"],
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Composez des rôles adaptés à votre organisation à partir des permissions ci-dessous. Les changements valent immédiatement pour les
          personnes qui détiennent le rôle.
        </p>
        {draft === null && <Button onClick={() => startFrom(null)}>Nouveau rôle</Button>}
      </div>
      {draft && (
        <Card title={draft.id ? `Modifier « ${draft.label} »` : "Nouveau rôle personnalisé"}>
          <RoleForm key={draft.id ?? "new"} draft={draft} groups={groups} grantable={grantable} onDone={() => { setDraft(null); refresh(); }} onCancel={() => setDraft(null)} />
        </Card>
      )}

      <Card title="Rôles personnalisés">
        {custom.length === 0 ? (
          <p className="text-sm text-muted">Aucun rôle personnalisé pour l'instant. Partez d'un rôle système ou d'une page blanche.</p>
        ) : (
          <ul className="divide-y divide-line" aria-label="Rôles personnalisés">
            {custom.map((role) => (
              <li key={role.id} className="py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">
                      {role.label} <span className="font-mono text-xs text-muted">{role.code}</span>
                    </p>
                    <p className="text-xs text-muted">
                      {SCOPE_LABELS[role.default_scope]} · {role.members} personne(s)
                    </p>
                  </div>
                  <span className="flex gap-3 text-xs">
                    <button
                      className="text-brand-700 hover:underline"
                      onClick={() => setDraft({ id: role.id, code: role.code, label: role.label, default_scope: role.default_scope as Draft["default_scope"], permissions: role.permissions })}
                      aria-label={`Modifier ${role.label}`}
                    >
                      Modifier
                    </button>
                    {confirm === role.id ? (
                      <span>
                        Supprimer ?{" "}
                        <button className="text-red-700 hover:underline" onClick={() => remove.mutate(role.id)}>
                          Oui
                        </button>{" "}
                        <button className="hover:underline" onClick={() => setConfirm(null)}>
                          Non
                        </button>
                      </span>
                    ) : (
                      <button className="text-red-700 hover:underline" onClick={() => setConfirm(role.id)}>
                        Supprimer
                      </button>
                    )}
                  </span>
                </div>
                <PermissionList codes={role.permissions} labels={labels} />
              </li>
            ))}
          </ul>
        )}
        {remove.error && <Alert>{errorMessage(remove.error)}</Alert>}
      </Card>

      <Card title="Rôles système (non modifiables)">
        <ul className="divide-y divide-line">
          {system.map((role) => (
            <li key={role.id} className="py-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-medium">
                  {role.label} <span className="text-xs text-muted">· {SCOPE_LABELS[role.default_scope]} · {role.members} personne(s)</span>
                </p>
                <button className="text-xs text-brand-700 hover:underline" onClick={() => startFrom(role)} aria-label={`Partir de ${role.label}`}>
                  Créer un rôle à partir de celui-ci
                </button>
              </div>
              <PermissionList codes={role.permissions} labels={labels} />
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">Les rôles du portail PME (dirigeant, collaborateur) restent fixes.</p>
      </Card>
    </div>
  );
}

function PermissionList({ codes, labels }: { codes: string[]; labels: Record<string, string> }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {codes.map((code) => (
        <Badge key={code} tone="neutral">
          {labels[code] ?? code}
        </Badge>
      ))}
    </div>
  );
}

function RoleForm({
  draft,
  groups,
  grantable,
  onDone,
  onCancel,
}: {
  draft: Draft;
  groups: Schemas["PermissionGroup"][];
  grantable: string[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState(draft);
  const save = useMutation({
    mutationFn: () => {
      const body = { label: form.label, default_scope: form.default_scope, permissions: form.permissions };
      return form.id
        ? unwrap(api.PATCH("/api/v1/config/roles/{role_id}", { params: { path: { role_id: form.id } }, body }))
        : unwrap(api.POST("/api/v1/config/roles", { body: { ...body, code: form.code.trim().toUpperCase() } }));
    },
    onSuccess: onDone,
  });
  const errors = save.error instanceof ApiError ? save.error.fieldErrors() : {};
  const toggle = (code: string) =>
    setForm({ ...form, permissions: form.permissions.includes(code) ? form.permissions.filter((c) => c !== code) : [...form.permissions, code] });

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        {form.id ? (
          <p className="text-sm">
            Code <span className="font-mono">{form.code}</span>
          </p>
        ) : (
          <TextInput label="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} hint="Ex. CHARGE_SUIVI" error={errors.code} required />
        )}
        <TextInput label="Libellé" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} error={errors.label} required />
        <SelectInput
          label="Périmètre par défaut"
          value={form.default_scope}
          onChange={(e) => setForm({ ...form, default_scope: e.target.value as Draft["default_scope"] })}
          placeholder="—"
          options={STAFF_SCOPES.map((s) => ({ value: s, label: SCOPE_LABELS[s] }))}
          hint={form.default_scope === "PORTEFEUILLE" ? "Les personnes pourront être assignées au suivi de PME." : undefined}
        />
      </div>
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium">Permissions</legend>
        {groups.map((group) => (
          <div key={group.label}>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{group.label}</p>
            {group.permissions.map((p) => {
              const allowed = grantable.includes(p.code);
              return (
                <label key={p.code} className="flex items-start gap-2 py-0.5 text-sm" title={allowed ? undefined : "Vous ne détenez pas cette permission."}>
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-brand-600"
                    checked={form.permissions.includes(p.code)}
                    disabled={!allowed && !form.permissions.includes(p.code)}
                    onChange={() => toggle(p.code)}
                  />
                  <span className={allowed ? "" : "text-muted"}>{p.label}</span>
                </label>
              );
            })}
          </div>
        ))}
      </fieldset>
      {errors.permissions && <p className="text-xs text-red-700">{errors.permissions}</p>}
      {save.error && Object.keys(errors).length === 0 && <Alert>{errorMessage(save.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" loading={save.isPending}>
          {form.id ? "Enregistrer le rôle" : "Créer le rôle"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
      </div>
    </form>
  );
}
