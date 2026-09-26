"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, type Schemas, unwrap } from "./api";

export type EditorTree = Schemas["FrameworkEditor"];
export type EditorDimension = Schemas["EditorDimension"];
export type EditorCriterion = Schemas["EditorCriterion"];
export type EditorQuestion = Schemas["EditorQuestion"];

export const QUESTION_TYPES: Record<Schemas["QuestionTypeEnum"], string> = {
  SINGLE: "Choix unique (niveaux)",
  BOOLEAN: "Oui / non",
  NUMBER: "Nombre",
  AMOUNT: "Montant (FCFA)",
  PERCENT: "Pourcentage",
  TEXT: "Texte libre",
};
export const AUDIENCES: Record<Schemas["TargetAudienceEnum"], string> = { PME: "PME", CONSEILLER: "Conseiller", LES_DEUX: "PME et conseiller" };
export const EVIDENCE_POLICIES: Record<Schemas["EvidencePolicyEnum"], string> = { NONE: "Aucune", RECOMMENDED: "Recommandée", REQUIRED: "Obligatoire" };
export const LEVEL_LABELS = ["Niveau 0", "Niveau 1", "Niveau 2", "Niveau 3", "Niveau 4"];

export const editorKey = (versionId: string) => ["framework-editor", versionId];

export function useFrameworkEditor(versionId: string) {
  return useQuery({
    queryKey: editorKey(versionId),
    queryFn: () => unwrap(api.GET("/api/v1/framework-versions/{version_id}/editor", { params: { path: { version_id: versionId } } })),
  });
}

/** Mutation d'édition : chaque appel renvoie l'arbre complet, qui remplace le cache. */
export function useEditorMutation<V>(versionId: string, call: (variables: V) => Promise<EditorTree>, onSuccess?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: call,
    onSuccess: (tree) => {
      queryClient.setQueryData(editorKey(versionId), tree);
      queryClient.invalidateQueries({ queryKey: ["framework-version", versionId] });
      onSuccess?.();
    },
  });
}

export function fieldErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError ? error.fieldErrors() : {};
}

/** Écart de poids affiché (« 95 / 100 ») : nombre sans décimales inutiles. */
export function points(value: string | number): string {
  const n = Number(value);
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}
