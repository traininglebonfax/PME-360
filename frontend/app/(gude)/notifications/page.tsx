"use client";

import { NotificationPreferences } from "@/components/NotificationPreferences";
import { PageHeader } from "@/components/ui";

export default function NotificationSettingsPage() {
  return (
    <>
      <PageHeader title="Notifications" subtitle="Choisissez comment être prévenu" />
      <NotificationPreferences />
    </>
  );
}
