"use client";

/**
 * Dépôt d'un document : fichier ou photo (mobile), progression, message clair en cas de refus.
 * Le document déposé n'est JAMAIS « conforme » d'office : il part en vérification (principe 4).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";

import { Alert, cx } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { ACCEPTED_FILES, type UploadFields, uploadDocument } from "@/lib/documents";

export function UploadButton({
  pmeId,
  fields,
  label = "Déposer",
  compact = false,
  onDone,
}: {
  pmeId: string;
  fields: UploadFields;
  label?: string;
  compact?: boolean;
  onDone?: () => void;
}) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const id = useId();

  const send = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setDone(false);
    setProgress(0);
    try {
      await uploadDocument(pmeId, file, fields, setProgress);
      setDone(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["folder", pmeId] }),
        queryClient.invalidateQueries({ queryKey: ["deadlines", pmeId] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      onDone?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setProgress(null);
      if (fileInput.current) fileInput.current.value = "";
      if (cameraInput.current) cameraInput.current.value = "";
    }
  };

  const button = "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium";
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex flex-wrap gap-2">
        <label
          htmlFor={`${id}-file`}
          className={cx(button, "cursor-pointer border-brand-600 bg-brand-600 text-white hover:bg-brand-700", progress !== null && "pointer-events-none opacity-60")}
        >
          {progress !== null ? `Envoi… ${Math.round(progress * 100)} %` : label}
        </label>
        <input id={`${id}-file`} ref={fileInput} type="file" accept={ACCEPTED_FILES} className="sr-only" onChange={(e) => send(e.target.files?.[0])} />
        {!compact && (
          <>
            <label htmlFor={`${id}-camera`} className={cx(button, "cursor-pointer border-line bg-white text-ink hover:bg-gray-50")}>
              Prendre une photo
            </label>
            <input id={`${id}-camera`} ref={cameraInput} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => send(e.target.files?.[0])} />
          </>
        )}
      </div>
      {done && <p className="text-xs text-brand-700">✓ Document reçu : il va être vérifié.</p>}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
