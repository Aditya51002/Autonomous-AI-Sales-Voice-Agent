"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "../lib/useCall";

interface Doc {
  id: number;
  name: string;
  chunks: number;
}

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${API_URL}${path}`, init).catch(() => {
    throw new Error("The API is not reachable. Is it running?");
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `The API returned ${response.status}.`);
  }
  return response.status === 204 ? null : response.json();
}

export function Documents() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const run = useCallback(async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setError("");
    try {
      await action();
      setDocuments(await request("/documents"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  }, []);

  useEffect(() => {
    void run("Loading documents…", async () => {});
  }, [run]);

  const upload = (files: File[]) =>
    run("Reading and indexing…", async () => {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        await request("/documents", { method: "POST", body: form });
      }
    });

  return (
    <section aria-label="Documents">
      <h2>Product documents</h2>
      <p>The agent answers product questions only from these. PDF, DOCX, Markdown or text.</p>
      <input
        type="file"
        multiple
        accept=".pdf,.docx,.md,.txt"
        aria-label="Upload documents"
        disabled={Boolean(busy)}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length) void upload(files);
        }}
      />
      {busy && <p role="status">{busy}</p>}
      {error && <p role="alert">{error}</p>}
      {documents.length === 0 && !busy && <p className="empty">No documents yet.</p>}
      <ul>
        {documents.map((doc) => (
          <li key={doc.id}>
            {doc.name} ({doc.chunks} passages){" "}
            <button
              disabled={Boolean(busy)}
              onClick={() => run("Removing…", () => request(`/documents/${doc.id}`, { method: "DELETE" }))}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
