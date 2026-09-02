"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

export function DemoUploader() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(
    (file: File) => {
      setError(null);
      if (!file.name.toLowerCase().endsWith(".dem")) {
        setError("O arquivo precisa ter extensão .dem");
        return;
      }
      setUploading(true);
      setProgress(0);

      // XHR em vez de fetch: precisamos do evento de progresso do upload.
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/demos");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        setUploading(false);
        if (xhr.status === 202) {
          const { jobId } = JSON.parse(xhr.responseText) as { jobId: string };
          router.push(`/jobs/${jobId}`);
        } else {
          try {
            setError(JSON.parse(xhr.responseText).error ?? "Falha no upload.");
          } catch {
            setError("Falha no upload.");
          }
        }
      };
      xhr.onerror = () => {
        setUploading(false);
        setError("Erro de rede no upload.");
      };
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    },
    [router],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) upload(file);
      }}
      onClick={() => !uploading && inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition ${
        dragging
          ? "border-[var(--accent)] bg-[var(--panel-2)]"
          : "border-[var(--border)] bg-[var(--panel)] hover:border-[var(--accent-2)]"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".dem"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
          e.target.value = "";
        }}
      />

      {uploading ? (
        <>
          <p className="text-sm text-[var(--muted)]">Enviando… {progress}%</p>
          <div className="mt-3 h-2 w-64 overflow-hidden rounded bg-[var(--panel-2)]">
            <div
              className="h-full bg-[var(--accent)] transition-[width]"
              style={{ width: `${progress}%` }}
            />
          </div>
        </>
      ) : (
        <>
          <p className="font-medium">Solte o .dem aqui ou clique para escolher</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Demos de CS2 (Source 2). Até 600 MB.
          </p>
        </>
      )}

      {error && <p className="mt-3 text-sm text-[var(--bad)]">{error}</p>}
    </div>
  );
}
