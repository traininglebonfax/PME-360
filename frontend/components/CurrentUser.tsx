"use client";

import { cx } from "@/components/ui";
import { initials } from "@/lib/format";
import { type Me, profileLabel } from "@/lib/session";

/** Identité de la personne connectée : nom et profil, visibles en permanence en haut de page. */
export function CurrentUser({ me, className }: { me: Me; className?: string }) {
  const profile = profileLabel(me);
  return (
    <div className={cx("flex min-w-0 items-center gap-2.5", className)} data-testid="current-user">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white"
        aria-hidden="true"
      >
        {initials(me.user.full_name)}
      </span>
      <div className="min-w-0 text-right leading-tight">
        <p className="truncate text-sm font-semibold text-ink">{me.user.full_name}</p>
        {profile && (
          <p className="mt-0.5 truncate">
            <span className="inline-flex items-center rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
              {profile}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}
