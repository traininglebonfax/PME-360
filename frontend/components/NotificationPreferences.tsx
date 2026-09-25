"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert, Badge, Card, LoadingBlock } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";

/** Choix des canaux par type d'événement ; les messages obligatoires ne se désactivent pas. */
export function NotificationPreferences() {
  const queryClient = useQueryClient();
  const preferences = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: () => unwrap(api.GET("/api/v1/me/notification-preferences")),
  });
  const save = useMutation({
    mutationFn: (items: Schemas["PreferenceRequest"][]) => unwrap(api.PUT("/api/v1/me/notification-preferences", { body: items })),
    onSuccess: (data) => queryClient.setQueryData(["notification-preferences"], data),
  });
  if (preferences.isLoading) return <LoadingBlock />;
  if (preferences.error) return <Alert>{errorMessage(preferences.error)}</Alert>;
  const toggle = (item: Schemas["Preference"], channel: "in_app" | "email") =>
    save.mutate([{ event_code: item.event_code, in_app: item.in_app, email: item.email, [channel]: !item[channel] }]);

  return (
    <Card title="Préférences de notification">
      <p className="mb-4 text-sm text-muted">SMS et WhatsApp arriveront en V2, selon les fournisseurs disponibles et votre accord.</p>
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="py-2 pr-4">Événement</th>
            <th className="py-2 pr-4 text-center">Dans l'application</th>
            <th className="py-2 text-center">E-mail</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {preferences.data!.map((item) => (
            <tr key={item.event_code}>
              <td className="py-2.5 pr-4">
                {item.label} {item.mandatory && <Badge tone="muted">Toujours envoyé</Badge>}
              </td>
              {(["in_app", "email"] as const).map((channel) => (
                <td key={channel} className="py-2.5 pr-4 text-center">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-brand-600"
                    aria-label={`${item.label} : ${channel === "email" ? "e-mail" : "application"}`}
                    checked={item.mandatory || item[channel]}
                    disabled={item.mandatory || save.isPending}
                    onChange={() => toggle(item, channel)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
