"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "../lib/useCall";
import { Icon } from "./Icons";

interface Doc {
  id: number;
  name: string;
  chunks: number;
}

const ACCEPTED = ".pdf,.docx,.md,.txt";

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
  const [over, setOver] = useState(false);

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

  const upload = (files: File[]) => {
    if (!files.length || busy) return;
    void run("Reading and indexing…", async () => {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        await request("/documents", { method: "POST", body: form });
      }
    });
  };

  return (
    <section className="card" aria-labelledby="documents-title">
      <div className="card-head">
        <h2 id="documents-title">Knowledge base</h2>
        <span className="muted">{documents.length > 0 && `${documents.length} documents`}</span>
      </div>
      <div className="card-body stack">
        <label
          className={`dropzone ${over ? "over" : ""} ${busy ? "disabled" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setOver(false);
            upload(Array.from(event.dataTransfer.files));
          }}
        >
          <Icon name="upload" size={24} />
          <strong>{busy || "Drop files here or choose files"}</strong>
          <span className="fact">
            PDF, DOCX, Markdown or text, up to 5 MB. The agent answers product questions from
            these.
          </span>
          <input
            className="sr-only"
            type="file"
            multiple
            accept={ACCEPTED}
            disabled={Boolean(busy)}
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              event.target.value = "";
              upload(files);
            }}
          />
        </label>

        {error && (
          <div className="notice" role="alert">
            <Icon name="alert" />
            <span>{error}</span>
          </div>
        )}
        {documents.length === 0 && !busy && !error && <p className="muted">No documents yet.</p>}

        {documents.length > 0 && (
          <ul className="list">
            {documents.map((doc) => (
              <li key={doc.id}>
                <Icon name="file" />
                <span className="grow">
                  {doc.name}
                  <small>{doc.chunks} passages</small>
                </span>
                <button
                  className="btn small"
                  disabled={Boolean(busy)}
                  aria-label={`Remove ${doc.name}`}
                  onClick={() => {
                    if (!window.confirm(`Remove ${doc.name} from the knowledge base?`)) return;
                    void run("Removing…", () =>
                      request(`/documents/${doc.id}`, { method: "DELETE" }),
                    );
                  }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
