"use client";

import { useParams } from "next/navigation";

import { PmeShell } from "@/components/PmeShell";
import { ActionDetail } from "@/components/plans/ActionDetail";

/** Fiche action côté PME : pourquoi, comment, documents à déposer. */
export default function PmeActionPage() {
  const { id } = useParams<{ id: string }>();
  return <PmeShell title="Action de mon plan">{() => <ActionDetail actionId={id} pmeView />}</PmeShell>;
}
