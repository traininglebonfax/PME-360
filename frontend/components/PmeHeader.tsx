"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandMark } from "@/components/Brand";
import { CurrentUser } from "@/components/CurrentUser";
import { NotificationBell } from "@/components/NotificationBell";
import { cx } from "@/components/ui";
import { useBrand } from "@/lib/brand";
import { type Me, useLogout } from "@/lib/session";

const PME_NAV = [
  { href: "/espace", label: "Accueil" },
  { href: "/espace/documents", label: "Mes documents" },
  { href: "/espace/plan", label: "Mon plan" },
  { href: "/espace/diagnostic", label: "Mon diagnostic" },
];

/** En-tête commun du portail PME : identité, notifications, déconnexion et menu toujours visible. */
export function PmeHeader({ me, width = "max-w-3xl" }: { me: Me; width?: string }) {
  const brand = useBrand();
  const logout = useLogout();
  const pathname = usePathname();
  return (
    <header className="border-b border-line bg-white">
      <div className={cx("mx-auto flex items-center justify-between gap-3 px-4 pt-3", width)}>
        <Link href="/espace" className="flex shrink-0 items-center gap-2">
          <BrandMark className="h-8 w-8" brand={brand} />
          <span className="hidden font-semibold sm:inline">Mon espace</span>
        </Link>
        <div className="flex min-w-0 items-center gap-2">
          <CurrentUser me={me} />
          <NotificationBell tone="light" preferencesHref="/espace/notifications" />
          <button onClick={logout} className="shrink-0 text-sm text-muted hover:text-ink">
            Se déconnecter
          </button>
        </div>
      </div>
      <nav aria-label="Menu de mon espace" className={cx("mx-auto flex gap-1 overflow-x-auto px-4 pt-2", width)}>
        {PME_NAV.map((item) => {
          const active = item.href === "/espace" ? pathname === "/espace" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "shrink-0 border-b-2 px-3 py-2 text-sm",
                active ? "border-brand-600 font-medium text-ink" : "border-transparent text-muted hover:text-ink",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
