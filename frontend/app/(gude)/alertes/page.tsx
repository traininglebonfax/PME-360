"use client";

import { AlertList } from "@/components/alerts/AlertList";
import { PageHeader } from "@/components/ui";

export default function AlertsPage() {
  return (
    <>
      <PageHeader title="Alertes" subtitle="Alertes ouvertes des PME de votre périmètre, des plus graves aux moins graves" />
      <AlertList showPme />
    </>
  );
}
