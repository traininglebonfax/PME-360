"use client";

/**
 * « Quels livrables restent systématiquement non fournis ? » (Document 9, § 4.2) : taux de non-fourniture et délai
 * moyen de fourniture, pour les livrables d'action et les documents d'obligation. Effectifs affichés ; un effectif
 * inférieur à 5 est signalé (taux peu fiable).
 */
import { useState } from "react";

import type { MissingDeliverables as Data } from "@/lib/dashboards";

function rate(value: number) {
  return `${Math.round(value * 100)} %`;
}

function days(value: number | null, signed = false) {
  if (value === null) return "—";
  const rounded = Math.round(value);
  if (signed && rounded < 0) return `${Math.abs(rounded)} j d'avance`;
  return `${rounded} j`;
}

function RateBar({ value }: { value: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-20 shrink-0 rounded-sm bg-gray-100" aria-hidden="true">
        <span className="block h-full rounded-sm bg-brand-600" style={{ width: `${Math.max(value * 100, value ? 3 : 0)}%` }} />
      </span>
      <span className="tabular-nums">{rate(value)}</span>
    </span>
  );
}

export function MissingDeliverables({ data }: { data: Data }) {
  const [view, setView] = useState<"deliverables" | "documents">("deliverables");
  const small = <span className="ml-1 rounded bg-amber-50 px-1 text-[10px] text-amber-800">effectif &lt; {data.min_cell}</span>;
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label="Type de pièces">
        {(
          [
            ["deliverables", `Livrables d'action (${data.deliverables.length})`],
            ["documents", `Documents d'obligation (${data.documents.length})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={view === key}
            onClick={() => setView(key)}
            className={
              view === key
                ? "rounded-md bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 ring-1 ring-brand-600"
                : "rounded-md px-2.5 py-1 text-xs text-muted ring-1 ring-line hover:text-ink"
            }
          >
            {label}
          </button>
        ))}
      </div>

      {view === "deliverables" ? (
        data.deliverables.length === 0 ? (
          <p className="text-sm text-muted">Aucun livrable n'a encore été demandé aux PME.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm" aria-label="Livrables d'action non fournis">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pr-3">Livrable</th>
                  <th className="py-2 pr-3 text-right">Demandés</th>
                  <th className="py-2 pr-3 text-right">Non fournis</th>
                  <th className="py-2 pr-3">Taux de non-fourniture</th>
                  <th className="py-2 text-right">Délai moyen de fourniture</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.deliverables.map((row) => (
                  <tr key={row.code}>
                    <td className="py-2 pr-3">
                      {row.name}
                      {row.small_sample && small}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{row.requested}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{row.missing}</td>
                    <td className="py-2 pr-3">
                      <RateBar value={row.missing_rate} />
                    </td>
                    <td className="py-2 text-right tabular-nums">{days(row.average_delay_days)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : data.documents.length === 0 ? (
        <p className="text-sm text-muted">Aucune échéance d'obligation n'est encore arrivée à terme.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm" aria-label="Documents d'obligation non fournis">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-3">Document</th>
                <th className="py-2 pr-3 text-right">Échéances échues</th>
                <th className="py-2 pr-3 text-right">Non fournis</th>
                <th className="py-2 pr-3 text-right">Fournis en retard</th>
                <th className="py-2 pr-3">Taux de non-fourniture</th>
                <th className="py-2 text-right">Retard moyen des dépôts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.documents.map((row) => (
                <tr key={row.code}>
                  <td className="py-2 pr-3">
                    {row.name}
                    {row.small_sample && small}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{row.due}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{row.missing}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{row.late}</td>
                  <td className="py-2 pr-3">
                    <RateBar value={row.missing_rate} />
                  </td>
                  <td className="py-2 text-right tabular-nums">{days(row.average_delay_days, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-muted">
        {view === "deliverables"
          ? `Un livrable est « non fourni » s'il n'a pas été déposé ${data.grace_days} jours après la demande (passage de l'action à « Document demandé ») ; le délai court de la demande au premier dépôt.`
          : "Une échéance échue est « non fournie » si aucun document n'a été déposé ; le retard se mesure du jour limite au premier dépôt (hors échéances dispensées)."}
      </p>
    </div>
  );
}
