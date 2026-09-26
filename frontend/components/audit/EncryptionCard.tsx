"use client";

/**
 * Chiffrement des fichiers (V1) : clé AES-256 propre à l'organisation, enveloppée par la clé maîtresse de la
 * plateforme. Aucune clé n'est jamais affichée ; l'administrateur peut renouveler la clé (les fichiers existants
 * restent lisibles avec leur version de clé).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function EncryptionCard() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["encryption"], queryFn: () => unwrap(api.GET("/api/v1/organization/encryption")) });
  const [confirm, setConfirm] = useState(false);
  const rotate = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/organization/encryption")),
    onSuccess: (data) => {
      setConfirm(false);
      queryClient.setQueryData(["encryption"], data);
      queryClient.invalidateQueries({ queryKey: ["audit-overview"] });
    },
  });
  if (status.isLoading || status.error) return null;
  const data = status.data!;
  const active = data.versions.find((v) => v.status === "ACTIVE");

  return (
    <Card
      title="Chiffrement des fichiers"
      action={data.enabled ? <Badge tone="brand">Actif</Badge> : <Badge tone="danger">Désactivé</Badge>}
    >
      <div className="space-y-3 text-sm" data-testid="encryption-card">
        <p className="text-muted">
          Chaque document et rapport est chiffré avant d'être stocké, avec une clé propre à l'organisation ({data.algorithm}). Un fichier déplacé
          ou modifié devient illisible.
        </p>
        {active ? (
          <p>
            Clé en vigueur : <span className="font-medium">version {active.version}</span>, créée le {formatDateTime(active.created_at)}
            {data.versions.length > 1 && ` · ${data.versions.length - 1} version(s) antérieure(s) conservée(s) en lecture seule`}.
          </p>
        ) : (
          <p className="text-muted">La clé sera créée au dépôt du premier fichier.</p>
        )}
        {data.can_rotate &&
          (confirm ? (
            <div className="flex flex-wrap items-center gap-2">
              <span>Créer une nouvelle clé ? Les nouveaux fichiers l'utiliseront ; les fichiers existants restent lisibles.</span>
              <Button loading={rotate.isPending} onClick={() => rotate.mutate()}>
                Oui, renouveler
              </Button>
              <Button variant="ghost" onClick={() => setConfirm(false)}>
                Annuler
              </Button>
            </div>
          ) : (
            <Button variant="secondary" onClick={() => setConfirm(true)}>
              Renouveler la clé de l'organisation
            </Button>
          ))}
        {rotate.error && <Alert>{errorMessage(rotate.error)}</Alert>}
      </div>
    </Card>
  );
}
