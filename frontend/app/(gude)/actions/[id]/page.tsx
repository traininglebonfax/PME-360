"use client";

import { useParams } from "next/navigation";

import { ActionDetail } from "@/components/plans/ActionDetail";

/** Fiche action côté équipe d'accompagnement. */
export default function ActionPage() {
  const { id } = useParams<{ id: string }>();
  return <ActionDetail actionId={id} />;
}
