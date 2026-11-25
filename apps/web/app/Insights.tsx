import type { Latency, Source } from "../lib/useCall";
import { Icon } from "./Icons";

export function Sources({ sources }: { sources: Source[] | null }) {
  return (
    <section className="card" aria-labelledby="sources-title">
      <div className="card-head">
        <h2 id="sources-title">Sources for the latest answer</h2>
      </div>
      <div className="card-body">
        {sources === null && <p className="muted">Passages used by the agent appear here.</p>}
        {sources?.length === 0 && <p className="muted">No matching passage in the documents.</p>}
        <ul className="list">
          {sources?.map((source, i) => (
            <li key={i}>
              <Icon name="file" />
              <span className="grow">
                {source.heading}
                <small>{source.document}</small>
              </span>
              <span className="pill" title="Similarity between the question and the passage">
                {source.score.toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const COLUMNS: { key: keyof Latency; label: string }[] = [
  { key: "stt_ms", label: "Transcript" },
  { key: "end_of_turn_ms", label: "End of turn" },
  { key: "llm_first_token_ms", label: "LLM" },
  { key: "tts_first_audio_ms", label: "Voice" },
  { key: "total_ms", label: "Total" },
];

function Tile({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="tile">
      <span>{label}</span>
      <strong>{value === undefined ? "–" : value.toLocaleString("en-IN")}</strong>
      {value !== undefined && <small>ms</small>}
    </div>
  );
}

export function LatencyPanel({ latencies }: { latencies: Latency[] }) {
  // The greeting has no total, so the tiles show the latest real reply.
  const reply = latencies.findLast((row) => row.total_ms !== undefined);

  return (
    <section className="card" aria-labelledby="latency-title">
      <div className="card-head">
        <h2 id="latency-title">Response time, latest reply</h2>
      </div>
      <div className="card-body">
        <div className="tiles">
          <Tile label="Total" value={reply?.total_ms} />
          <Tile label="LLM first token" value={reply?.llm_first_token_ms} />
          <Tile label="First audio" value={reply?.tts_first_audio_ms} />
        </div>
        <p className="fact" style={{ marginTop: 10 }}>
          Total starts when the speech service detects the end of speech.
        </p>
        {latencies.length > 0 && (
          <details>
            <summary>All turns (milliseconds)</summary>
            <div className="table">
              <table>
                <thead>
                  <tr>
                    <th>Turn</th>
                    {COLUMNS.map((c) => (
                      <th key={c.key}>{c.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {latencies.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {row.role === "user" ? "You" : "Agent"} · {row.language}
                      </td>
                      {COLUMNS.map((c) => (
                        <td key={c.key}>{row[c.key] ?? "–"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </section>
  );
}
