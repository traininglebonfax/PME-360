"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useGuard } from "@/components/AppShell";
import { BrandMark } from "@/components/Brand";
import { NotificationBell } from "@/components/NotificationBell";
import { LoadingBlock } from "@/components/ui";
import type { Me } from "@/lib/session";
import { useBrand } from "@/lib/brand";

/** En-tête simple du portail PME (mobile d'abord) et garde d'accès. */
export function PmeShell({ title, subtitle, children }: { title: string; subtitle?: string; children: (me: Me) => ReactNode }) {
  const { me, isLoading } = useGuard("pme");
  const brand = useBrand();
  if (isLoading || !me) return <LoadingBlock />;
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link href="/espace" className="flex items-center gap-2">
            <BrandMark className="h-8 w-8" brand={brand} />
            <span className="font-semibold">Mon espace</span>
          </Link>
          <div className="flex items-center gap-2">
            <NotificationBell tone="light" preferencesHref="/espace/notifications" />
            <Link href="/espace" className="text-sm text-muted hover:text-ink">
              ← Accueil
            </Link>
          </div>
        </div>
      </header>
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
