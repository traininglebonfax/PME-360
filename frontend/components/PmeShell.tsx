"use client";

import type { ReactNode } from "react";

import { useGuard } from "@/components/AppShell";
import { PmeHeader } from "@/components/PmeHeader";
import { LoadingBlock } from "@/components/ui";
import type { Me } from "@/lib/session";

/** Gabarit du portail PME (mobile d'abord) et garde d'accès. */
export function PmeShell({ title, subtitle, children }: { title: string; subtitle?: string; children: (me: Me) => ReactNode }) {
  const { me, isLoading } = useGuard("pme");
  if (isLoading || !me) return <LoadingBlock />;
  return (
    <div className="min-h-screen">
      <PmeHeader me={me} />
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <div>
          <h1 className="text-xl font-semibold">{title}</h1>
          {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
        </div>
        {children(me)}
      </main>
    </div>
  );
}
