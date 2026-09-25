"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingBlock } from "@/components/ui";
import { homeFor, useMe } from "@/lib/session";

/** Aiguillage : connexion, portail PME ou portail GUDE-PME selon l'utilisateur. */
export default function Home() {
  const router = useRouter();
  const { data: me, isLoading } = useMe();

  useEffect(() => {
    if (isLoading) return;
    router.replace(me ? homeFor(me) : "/connexion");
  }, [me, isLoading, router]);

  return <LoadingBlock />;
}
