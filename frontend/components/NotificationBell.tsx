"use client";

/** Notifications in-app (Document 7, § 8.3) : compteur, liste récente, tout marquer comme lu. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { cx } from "@/components/ui";
import { api, unwrap } from "@/lib/api";
import { formatRelative } from "@/lib/format";

export function NotificationBell({ tone = "dark", preferencesHref }: { tone?: "dark" | "light"; preferencesHref: string }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const count = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => unwrap(api.GET("/api/v1/notifications/unread-count")),
    refetchInterval: 60_000,
  });
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => unwrap(api.GET("/api/v1/notifications")),
    enabled: open,
  });
  const markRead = useMutation({
    mutationFn: (body: { ids?: string[]; all?: boolean }) =>
      unwrap(api.POST("/api/v1/notifications/read", { body: { ids: body.ids ?? [], all: body.all ?? false } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  useEffect(() => {
    const close = (event: MouseEvent) => panel.current && !panel.current.contains(event.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const unread = count.data?.unread ?? 0;

  return (
    <div className="relative" ref={panel}>
      <button
        onClick={() => setOpen(!open)}
        aria-label={`Notifications${unread ? ` (${unread} non lues)` : ""}`}
        aria-expanded={open}
        className={cx("relative rounded-md p-2", tone === "dark" ? "text-brand-100 hover:bg-white/10 hover:text-white" : "text-muted hover:bg-gray-100 hover:text-ink")}
      >
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 overflow-hidden rounded-xl border border-line bg-white text-ink shadow-lg sm:left-0 sm:right-auto">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <p className="text-sm font-semibold">Notifications</p>
            {unread > 0 && (
              <button className="text-xs text-brand-700 hover:underline" onClick={() => markRead.mutate({ all: true })}>
                Tout marquer comme lu
              </button>
            )}
          </div>
          <ul className="max-h-96 divide-y divide-line overflow-y-auto">
            {(list.data ?? []).slice(0, 15).map((notification) => (
              <li key={notification.id}>
                <button
                  className={cx("block w-full px-4 py-2.5 text-left hover:bg-gray-50", !notification.read_at && "bg-brand-50/60")}
                  onClick={() => {
                    markRead.mutate({ ids: [notification.id] });
                    setOpen(false);
                    if (notification.link) router.push(notification.link);
                  }}
                >
                  <p className="text-sm font-medium">{notification.title}</p>
                  <p className="line-clamp-2 text-xs text-muted">{notification.body}</p>
                  <p className="mt-0.5 text-[11px] text-muted">{formatRelative(notification.created_at)}</p>
                </button>
              </li>
            ))}
            {list.data?.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">Aucune notification.</li>}
          </ul>
          <Link href={preferencesHref} onClick={() => setOpen(false)} className="block border-t border-line px-4 py-2.5 text-xs text-brand-700 hover:bg-gray-50">
            Préférences de notification
          </Link>
        </div>
      )}
    </div>
  );
}
