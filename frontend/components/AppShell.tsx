"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { BrandMark } from "@/components/Brand";
import { CurrentUser } from "@/components/CurrentUser";
import { NotificationBell } from "@/components/NotificationBell";
import { cx, LoadingBlock } from "@/components/ui";
import { api, unwrap } from "@/lib/api";
import { initials } from "@/lib/format";
import { hasPermission, homeFor, type Me, profileLabel, useLogout, useMe } from "@/lib/session";
import { type Brand, DEFAULT_BRAND, useApplyBrand, useBrand } from "@/lib/brand";

interface NavItem {
  href: string;
  label: string;
  permission?: string;
}

const GUDE_NAV: NavItem[] = [
  { href: "/tableau-de-bord", label: "Tableau de bord", permission: "pme.view" },
  { href: "/pme", label: "PME", permission: "pme.view" },
  { href: "/portefeuille", label: "Portefeuille", permission: "dashboard.portfolio" },
  { href: "/analyses", label: "Analyses", permission: "dashboard.portfolio" },
  { href: "/rapports", label: "Rapports", permission: "dashboard.portfolio" },
  { href: "/verifications", label: "Documents à vérifier", permission: "document.verify" },
  { href: "/alertes", label: "Alertes", permission: "pme.view" },
  { href: "/assistant", label: "Copilot", permission: "ai.ask" },
  { href: "/referentiel", label: "Référentiel", permission: "pme.view" },
  { href: "/conformite", label: "Conformité et obligations", permission: "org.configure" },
  { href: "/accompagnement", label: "Accompagnement", permission: "org.configure" },
  { href: "/modeles-notification", label: "Modèles de notification", permission: "org.configure" },
  { href: "/workflows", label: "Workflows", permission: "org.configure" },
  { href: "/identite", label: "Identité de l'organisation", permission: "org.configure" },
  { href: "/ia", label: "Intelligence artificielle", permission: "ai.review" },
  { href: "/programmes", label: "Programmes", permission: "programme.manage" },
  { href: "/utilisateurs", label: "Utilisateurs", permission: "org.manage_users" },
  { href: "/audit", label: "Tableau de bord auditeur", permission: "audit.view" },
  { href: "/journal", label: "Journal d'audit", permission: "audit.view" },
];

/** Garde d'accès : redirige si l'utilisateur n'est pas connecté ou n'appartient pas à ce portail. */
export function useGuard(portal: Me["portal"]) {
  const router = useRouter();
  const query = useMe();
  const me = query.data;
  // Identité de l'organisation (couleurs, titre) appliquée à tout le portail.
  useApplyBrand((me?.organization?.brand as Brand | undefined) ?? DEFAULT_BRAND);
  useEffect(() => {
    if (query.isLoading) return;
    if (!me) router.replace("/connexion");
    else if (me.portal !== portal) router.replace(homeFor(me));
  }, [me, query.isLoading, portal, router]);
  return { me: me && me.portal === portal ? me : null, isLoading: query.isLoading };
}

function OrganizationSwitcher({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const organizations = Array.from(new Map(me.memberships.map((m) => [m.organization_id, m.organization_name])));
  if (organizations.length < 2) return <p className="truncate text-xs text-brand-100">{me.organization?.name}</p>;
  return (
    <select
      aria-label="Organisation active"
      className="mt-1 w-full rounded-md border-0 bg-brand-700 px-2 py-1 text-xs text-white"
      value={me.organization?.id ?? ""}
      onChange={async (event) => {
        await unwrap(api.POST("/api/v1/auth/switch-organization", { body: { organization_id: event.target.value } }));
        queryClient.clear();
        router.replace("/");
      }}
    >
      {organizations.map(([id, name]) => (
        <option key={id} value={id}>
          {name}
        </option>
      ))}
    </select>
  );
}

export function GudeShell({ children }: { children: ReactNode }) {
  const { me, isLoading } = useGuard("gude");
  const pathname = usePathname();
  const logout = useLogout();
  const brand = useBrand();
  const [open, setOpen] = useState(false);

  if (isLoading || !me) return <LoadingBlock />;
  const nav = GUDE_NAV.filter((item) => !item.permission || hasPermission(me, item.permission));

  return (
    <div className="min-h-screen lg:flex">
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-30 w-64 flex-col bg-brand-800 text-white transition-transform lg:static lg:flex lg:translate-x-0",
          open ? "flex translate-x-0" : "hidden -translate-x-full lg:flex",
        )}
      >
        <div className="flex items-center gap-2.5 px-5 py-5">
          <BrandMark className="h-8 w-8" brand={brand} />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">{brand.product_name}</p>
            <OrganizationSwitcher me={me} />
          </div>
          <NotificationBell preferencesHref="/notifications" />
        </div>
        <nav className="flex-1 space-y-1 px-3" aria-label="Navigation principale">
          {nav.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "block rounded-lg px-3 py-2 text-sm",
                  active ? "bg-white/15 font-medium text-white" : "text-brand-100 hover:bg-white/10 hover:text-white",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-sm font-medium">
              {initials(me.user.full_name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{me.user.full_name}</p>
              <p className="truncate text-xs text-brand-100">{profileLabel(me)}</p>
            </div>
          </div>
          <button onClick={logout} className="mt-3 text-xs text-brand-100 hover:text-white hover:underline">
            Se déconnecter
          </button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden="true" />}
      <div className="min-w-0 flex-1">
        <header className="flex items-center gap-3 border-b border-line bg-white px-4 py-2.5 sm:px-6 lg:px-8">
          <button onClick={() => setOpen(true)} className="rounded-md p-2 text-ink hover:bg-gray-100 lg:hidden" aria-label="Ouvrir le menu">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
            </svg>
          </button>
          <p className="font-semibold lg:hidden">{brand.product_name}</p>
          <CurrentUser me={me} className="ml-auto" />
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
