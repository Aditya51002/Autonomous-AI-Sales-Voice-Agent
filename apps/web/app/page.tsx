"use client";

import { useState } from "react";
import { type Latency, useCall } from "../lib/useCall";
import { Documents } from "./Documents";
import { LeadPanel } from "./LeadPanel";

const COLUMNS: { key: keyof Latency; label: string }[] = [
  { key: "stt_ms", label: "Transcript" },
  { key: "end_of_turn_ms", label: "End of turn" },
  { key: "llm_first_token_ms", label: "LLM first token" },
  { key: "tts_first_audio_ms", label: "TTS first audio" },
  { key: "total_ms", label: "Total" },
];

export default function Home() {
  const call = useCall();
  const [consent, setConsent] = useState(false);
  const live = call.status === "live";

  return (
    <main>
      <h1>AI Sales Voice Agent</h1>
      <p>Talk in English, Hindi or Hinglish. You can interrupt at any time.</p>

      {call.status === "idle" && (
        <label>
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          I agree to speak with an AI assistant and to have the call transcribed.
        </label>
      )}

      <div className="controls">
        {call.status === "idle" ? (
          <button onClick={call.start} disabled={!consent}>
            Start call
          </button>
        ) : (
          <>
            <button onClick={call.end}>End call</button>
            <button onClick={call.toggleMute} disabled={!live}>
              {call.muted ? "Unmute" : "Mute"}
            </button>
          </>
        )}
        <span role="status">
          {call.status === "connecting" && "Connecting…"}
          {live && (call.agentState ? `Agent: ${call.agentState}` : "Waiting for the agent…")}
        </span>
      </div>

      {call.status === "idle" && call.remembered && (
        <p>
          This browser is remembered from an earlier call.{" "}
          <button onClick={call.forget}>Forget me and erase my data</button>
        </p>
      )}

      {call.error && <p role="alert">{call.error}</p>}

      <section aria-label="Transcript">
        <h2>Transcript</h2>
        {call.lines.length === 0 && <p className="empty">The conversation appears here.</p>}
        {call.lines.map((line) => (
          <p key={line.id} className={line.speaker}>
            <strong>{line.speaker === "you" ? "You" : "Agent"}:</strong> {line.text}
          </p>
        ))}
      </section>

      <LeadPanel lead={call.lead} />

      <section aria-label="Sources">
        <h2>Sources for the latest answer</h2>
        {call.sources === null && <p className="empty">Passages used by the agent appear here.</p>}
        {call.sources?.length === 0 && <p>No matching passage in the documents.</p>}
        <ul>
          {call.sources?.map((source, i) => (
            <li key={i}>
              {source.document}: {source.heading} (similarity {source.score})
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Latency">
        <h2>Latency per turn (ms)</h2>
        <div className="table">
          <table>
            <thead>
              <tr>
                <th>Speaker</th>
                <th>Language</th>
                {COLUMNS.map((c) => (
                  <th key={c.key}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {call.latencies.map((row) => (
                <tr key={row.id}>
                  <td>{row.role === "user" ? "You" : "Agent"}</td>
                  <td>{row.language}</td>
                  {COLUMNS.map((c) => (
                    <td key={c.key}>{row[c.key] ?? "–"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Documents />
    </main>
  );
}
