"use client";

import { NotificationPreferences } from "@/components/NotificationPreferences";
import { PmeShell } from "@/components/PmeShell";

export default function PmeNotificationsPage() {
  return <PmeShell title="Mes notifications">{() => <NotificationPreferences />}</PmeShell>;
}
