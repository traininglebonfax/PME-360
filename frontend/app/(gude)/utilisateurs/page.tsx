"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RolesAdmin } from "@/components/users/RolesAdmin";
import { Alert, Badge, Button, Card, cx, LoadingBlock, PageHeader, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { SCOPE_LABELS } from "@/lib/labels";

const EMPTY = { email: "", full_name: "", phone: "", role: "CONSEILLER", scope_ref_id: "" };

export default function UsersPage() {
  const [tab, setTab] = useState<"membres" | "roles">("membres");
  return (
    <>
      <PageHeader title="Utilisateurs" subtitle="Équipes, experts, auditeurs et comptes PME de l'organisation ; rôles et permissions" />
      <div className="mb-6 flex gap-1 border-b border-line" role="tablist">
        {(
          [
            ["membres", "Membres et invitations"],
            ["roles", "Rôles et permissions"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cx("border-b-2 px-3 py-2.5 text-sm", tab === key ? "border-brand-600 font-medium text-brand-800" : "border-transparent text-muted")}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "membres" ? <Members /> : <RolesAdmin />}
    </>
  );
}

function Members() {
  const queryClient = useQueryClient();
  const members = useQuery({ queryKey: ["members"], queryFn: () => unwrap(api.GET("/api/v1/users")) });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => unwrap(api.GET("/api/v1/roles")) });
  const programmes = useQuery({ queryKey: ["programmes"], queryFn: () => unwrap(api.GET("/api/v1/programmes")) });
  const pmes = useQuery({ queryKey: ["pmes", "all-for-invite"], queryFn: () => unwrap(api.GET("/api/v1/pmes", { params: { query: { page_size: 100, ordering: "legal_name" } } })) });
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState<string | null>(null);

  const role = roles.data?.find((r) => r.code === form.role);
  const scope = role?.default_scope;

  const invite = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/users/invite", {
          body: {
            email: form.email,
            full_name: form.full_name,
            phone: form.phone,
            role: form.role,
            scope: scope as Schemas["ScopeEnum"],
            scope_ref_id: form.scope_ref_id || null,
          },
        }),
      ),
    onSuccess: () => {
      setDone(`Invitation envoyée à ${form.email}.`);
      setForm(EMPTY);
      setErrors({});
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (err) => {
      setDone(null);
      setErrors(err instanceof ApiError ? err.fieldErrors() : {});
    },
  });
  const revoke = useMutation({
    mutationFn: (membershipId: string) =>
      unwrap(api.POST("/api/v1/memberships/{membership_id}/revoke", { params: { path: { membership_id: membershipId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
  });

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Membres" className="lg:col-span-2">
          {members.isLoading ? (
            <LoadingBlock />
          ) : members.error ? (
            <Alert>{errorMessage(members.error)}</Alert>
          ) : (
            <ul className="divide-y divide-line">
              {members.data!.map((member) => (
                <li key={member.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{member.full_name}</p>
                      <p className="text-sm text-muted">
                        {member.email} · dernière connexion {formatRelative(member.last_login)}
                        {!member.mfa_enabled && member.memberships.some((m) => !m.role.endsWith("_PME")) && (
                          <span className="ml-1 text-amber-700">· MFA non activée</span>
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {member.memberships.map((membership) => (
                      <span key={membership.id} className="inline-flex items-center gap-1.5">
                        <Badge tone={membership.is_active ? "brand" : "muted"}>
                          {membership.role_label} · {SCOPE_LABELS[membership.scope]}
                          {!membership.is_active && " (retiré)"}
                        </Badge>
                        {membership.is_active && (
                          <button
                            className="text-xs text-muted hover:text-red-700"
                            onClick={() => revoke.mutate(membership.id)}
                            aria-label={`Retirer l'accès ${membership.role_label} de ${member.full_name}`}
                          >
                            Retirer
                          </button>
                        )}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {revoke.error && <Alert>{errorMessage(revoke.error)}</Alert>}
        </Card>
        <Card title="Inviter un utilisateur">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              invite.mutate();
            }}
          >
            {done && <Alert tone="success">{done}</Alert>}
            {invite.error && !(invite.error instanceof ApiError && invite.error.code === "validation_error") && (
              <Alert>{errorMessage(invite.error)}</Alert>
            )}
            <TextInput label="Nom complet" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required error={errors.full_name} />
            <TextInput label="E-mail" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required error={errors.email} />
            <TextInput label="Téléphone" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <SelectInput
              label="Rôle"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value, scope_ref_id: "" })}
              options={(roles.data ?? []).map((r) => ({ value: r.code, label: r.label }))}
              error={errors.role}
              required
            />
            {scope && <p className="text-xs text-muted">Périmètre : {SCOPE_LABELS[scope]}</p>}
            {scope === "PROGRAMME" && (
              <SelectInput
                label="Programme"
                value={form.scope_ref_id}
                onChange={(e) => setForm({ ...form, scope_ref_id: e.target.value })}
                options={(programmes.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
                error={errors.scope_ref_id}
                required
              />
            )}
            {scope === "PME" && (
              <SelectInput
                label="PME"
                value={form.scope_ref_id}
                onChange={(e) => setForm({ ...form, scope_ref_id: e.target.value })}
                options={(pmes.data?.results ?? []).map((p) => ({ value: p.id, label: p.legal_name }))}
                error={errors.scope_ref_id}
                required
              />
            )}
            <Button type="submit" loading={invite.isPending}>
              Envoyer l'invitation
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
