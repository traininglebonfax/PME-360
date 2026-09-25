"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Pas de nouvelle tentative sur les erreurs d'accès ou de validation : seulement sur le réseau / 5xx.
            retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
