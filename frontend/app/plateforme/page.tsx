"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useGuard } from "@/components/AppShell";
import { BrandName } from "@/components/Brand";
import { Alert, Badge, Button, Card, LoadingBlock, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useLogout } from "@/lib/session";

const TYPES: Record<Schemas["TypeEnum"], string> = {
  AGENCE_PUBLIQUE: "Agence ou programme public",
  BANQUE: "Banque",
  INCUBATEUR: "Incubateur",
  ONG: "ONG",
  BAILLEUR: "Bailleur",
  CABINET: "Cabinet",
  ASSOCIATION: "Association professionnelle",
};

/** Administration plateforme : création des organisations. Aucun accès aux données des PME. */
export default function PlatformPage() {
  const { me, isLoading } = useGuard("platform");
  const logout = useLogout();
  const queryClient = useQueryClient();
  const organizations = useQuery({
    queryKey: ["platform-organizations"],
    queryFn: () => unwrap(api.GET("/api/v1/platform/organizations")),
    enabled: Boolean(me),
  });
  const [form, setForm] = useState({ name: "", slug: "", type: "AGENCE_PUBLIQUE", admin_email: "", admin_full_name: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/platform/organizations", { body: { ...form, type: form.type as Schemas["TypeEnum"] } })),
    onSuccess: () => {
      setForm({ name: "", slug: "", type: "AGENCE_PUBLIQUE", admin_email: "", admin_full_name: "" });
      setErrors({});
      queryClient.invalidateQueries({ queryKey: ["platform-organizations"] });
    },
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });

  if (isLoading || !me) return <LoadingBlock />;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <BrandName name="PME360 · Plateforme" />
        <button onClick={logout} className="text-sm text-muted hover:text-ink">
          Se déconnecter
        </button>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Organisations" className="lg:col-span-2">
          {organizations.isLoading ? (
            <LoadingBlock />
          ) : organizations.error ? (
            <Alert>{errorMessage(organizations.error)}</Alert>
          ) : (
            <ul className="divide-y divide-line">
              {organizations.data!.map((org) => (
                <li key={org.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="font-medium">{org.name}</p>
                    <p className="text-sm text-muted">
                      {TYPES[org.type]} · {org.slug} · créée le {formatDate(org.created_at)}
                    </p>
                  </div>
                  <Badge tone={org.status === "ACTIVE" ? "brand" : "muted"}>{org.status === "ACTIVE" ? "Active" : "Suspendue"}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Nouvelle organisation">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            {create.error && !(create.error instanceof ApiError && create.error.code === "validation_error") && <Alert>{errorMessage(create.error)}</Alert>}
            <TextInput label="Nom" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required error={errors.name} />
            <TextInput
              label="Identifiant"
              hint="Lettres minuscules, chiffres et tirets"
              pattern="[a-z0-9-]+"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
              required
              error={errors.slug}
            />
            <SelectInput label="Type" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} options={Object.entries(TYPES).map(([value, label]) => ({ value, label }))} />
            <TextInput label="Administrateur : nom" value={form.admin_full_name} onChange={(e) => setForm({ ...form, admin_full_name: e.target.value })} required />
            <TextInput label="Administrateur : e-mail" type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} required error={errors.admin_email} />
            <Button type="submit" loading={create.isPending}>
              Créer l'organisation
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
