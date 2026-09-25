"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Button, Card, EmptyState, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api";
import { formatDate } from "@/lib/format";

export default function ProgrammesPage() {
  const queryClient = useQueryClient();
  const programmes = useQuery({ queryKey: ["programmes"], queryFn: () => unwrap(api.GET("/api/v1/programmes")) });
  const [form, setForm] = useState({ name: "", funder: "", start_date: "", end_date: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [cohortNames, setCohortNames] = useState<Record<string, string>>({});

  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/programmes", {
          body: { name: form.name, funder: form.funder, start_date: form.start_date || null, end_date: form.end_date || null },
        }),
      ),
    onSuccess: () => {
      setForm({ name: "", funder: "", start_date: "", end_date: "" });
      setErrors({});
      queryClient.invalidateQueries({ queryKey: ["programmes"] });
    },
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });
  const addCohort = useMutation({
    mutationFn: (programmeId: string) =>
      unwrap(api.POST("/api/v1/programmes/{id}/cohorts", { params: { path: { id: programmeId } }, body: { name: cohortNames[programmeId] ?? "" } })),
    onSuccess: (_, programmeId) => {
      setCohortNames((current) => ({ ...current, [programmeId]: "" }));
      queryClient.invalidateQueries({ queryKey: ["programmes"] });
    },
  });

  return (
    <>
      <PageHeader title="Programmes" subtitle="Programmes d'accompagnement et cohortes de PME" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {programmes.isLoading ? (
            <LoadingBlock />
          ) : programmes.error ? (
            <Alert>{errorMessage(programmes.error)}</Alert>
          ) : programmes.data!.length === 0 ? (
            <EmptyState title="Aucun programme">Créez un premier programme pour y inscrire des cohortes de PME.</EmptyState>
          ) : (
            programmes.data!.map((programme) => (
              <Card key={programme.id} title={programme.name}>
                <p className="text-sm text-muted">
                  {formatDate(programme.start_date)} → {formatDate(programme.end_date)}
                  {programme.funder && ` · financé par ${programme.funder}`}
                </p>
                <ul className="mt-3 flex flex-wrap gap-2">
                  {programme.cohorts.map((cohort) => (
                    <li key={cohort.id} className="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-800">
                      {cohort.name}
                    </li>
                  ))}
                </ul>
                <form
                  className="mt-4 flex items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    addCohort.mutate(programme.id);
                  }}
                >
                  <div className="flex-1">
                    <TextInput
                      label="Nouvelle cohorte"
                      value={cohortNames[programme.id] ?? ""}
                      onChange={(e) => setCohortNames((c) => ({ ...c, [programme.id]: e.target.value }))}
                      required
                    />
                  </div>
                  <Button type="submit" variant="secondary" loading={addCohort.isPending && addCohort.variables === programme.id}>
                    Ajouter
                  </Button>
                </form>
              </Card>
            ))
          )}
        </div>
        <Card title="Nouveau programme">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            {create.error && !(create.error instanceof ApiError && create.error.code === "validation_error") && <Alert>{errorMessage(create.error)}</Alert>}
            <TextInput label="Nom" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required error={errors.name} />
            <TextInput label="Bailleur" value={form.funder} onChange={(e) => setForm({ ...form, funder: e.target.value })} />
            <TextInput label="Début" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            <TextInput label="Fin" type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} error={errors.end_date} />
            <Button type="submit" loading={create.isPending}>
              Créer
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
