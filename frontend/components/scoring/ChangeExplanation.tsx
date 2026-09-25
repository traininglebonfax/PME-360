/**
 * Explication d'une évolution de score (Document 6, § 8). Barres divergentes autour d'une ligne zéro neutre :
 * hausse en vert, baisse en orange (paire validée pour le daltonisme), toujours doublées du signe et de la valeur.
 */
import { Badge } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { type ChangeExplanation as Explanation, formatScore } from "@/lib/scoring";

const POSITIVE = "#16825d";
const NEGATIVE = "#c2410c";

function signed(value: number): string {
  const text = Math.abs(value).toFixed(1).replace(".", ",");
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : "0";
}

const NATURE_LABELS: Record<string, string> = {
  PROGRES: "progrès",
  RECUL: "recul",
  GAIN_DE_PREUVE: "gain de preuve",
};

export function ChangeExplanation({ explanation }: { explanation: Explanation }) {
  const max = Math.max(0.5, ...explanation.contributions.map((c) => Math.abs(c.contribution)));
  const delta = explanation.delta_global;
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink">
        <span className="text-lg font-semibold">
          {delta === null ? "—" : `${signed(delta)} points`}
        </span>{" "}
        entre le {formatDate(explanation.before.reference_date)} ({formatScore(explanation.before.global_score)}) et le{" "}
        {formatDate(explanation.after.reference_date)} ({formatScore(explanation.after.global_score)})
      </p>
      {explanation.reprojected_baseline && (
        <p className="text-xs text-muted">
          Le référentiel a changé ({explanation.before.framework_version} → {explanation.after.framework_version}) : le point de
          départ a été recalculé avec la nouvelle version pour comparer ce qui est comparable (valeur d'origine :{" "}
          {formatScore(explanation.before.original_global_score)}).
        </p>
      )}
      <ul className="space-y-2">
        {explanation.contributions
          .filter((c) => Math.abs(c.contribution) >= 0.05)
          .map((c) => (
            <li key={c.dimension} className="grid grid-cols-[8rem_1fr_3.5rem] items-center gap-3 text-sm">
              <span className="truncate text-ink" title={c.name}>
                {c.name}
              </span>
              <span className="relative h-3" aria-hidden="true">
                <span className="absolute inset-y-0 left-1/2 w-px bg-gray-300" />
                <span
                  className="absolute inset-y-0 rounded-sm"
                  style={{
                    background: c.contribution >= 0 ? POSITIVE : NEGATIVE,
                    left: c.contribution >= 0 ? "50%" : `${50 - (Math.abs(c.contribution) / max) * 50}%`,
                    width: `${(Math.abs(c.contribution) / max) * 50}%`,
                  }}
                  title={c.criteria.map((d) => `${d.criterion} ${signed(d.contribution)} (${NATURE_LABELS[d.nature]})`).join("\n")}
                />
              </span>
              <span className="text-right font-medium tabular-nums text-ink">{signed(c.contribution)}</span>
            </li>
          ))}
      </ul>
      {explanation.other !== null && Math.abs(explanation.other) >= 0.1 && (
        <p className="text-xs text-muted">
          Autres effets ({signed(explanation.other)} pt) : dimensions devenues évaluables ou non, et renormalisation des poids.
        </p>
      )}
      {explanation.proof_gain > 0 && (
        <p className="text-xs text-muted">
          <Badge tone="info">Gain de preuve</Badge> Environ {signed(explanation.proof_gain)} pt proviennent de preuves nouvellement
          vérifiées sur des pratiques qui existaient déjà : une meilleure <strong>mesure</strong>, pas nécessairement un progrès réel.
        </p>
      )}
    </div>
  );
}
