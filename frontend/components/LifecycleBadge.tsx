import { Badge } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { LIFECYCLE_LABELS, LIFECYCLE_TONES } from "@/lib/labels";

export function LifecycleBadge({ status }: { status: string }) {
  const key = status as Schemas["LifecycleStatusEnum"];
  return <Badge tone={LIFECYCLE_TONES[key] ?? "neutral"}>{LIFECYCLE_LABELS[key] ?? status}</Badge>;
}
