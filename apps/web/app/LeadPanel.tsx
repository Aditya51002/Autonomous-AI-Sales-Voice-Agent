import type { Criterion, LeadState } from "../lib/useCall";
import { Icon } from "./Icons";

const CRITERIA: { key: Criterion; label: string; max: number }[] = [
  { key: "need", label: "Need", max: 30 },
  { key: "budget", label: "Budget", max: 25 },
  { key: "authority", label: "Authority", max: 20 },
  { key: "timeline", label: "Timeline", max: 25 },
];

const GRADE_DOT = { Hot: "good", Warm: "warning", Cold: "" };

const SENTIMENTS = [
  { key: "positive", label: "Positive", dot: "good" },
  { key: "neutral", label: "Neutral", dot: "" },
  { key: "negative", label: "Negative", dot: "critical" },
] as const;

function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div
      className="meter"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
    >
      <div style={{ width: `${(value / max) * 100}%` }} />
    </div>
  );
}

export function LeadPanel({ lead }: { lead: LeadState | null }) {
  const identity = lead && [lead.facts.name, lead.facts.company].filter(Boolean).join(" · ");

  return (
    <section className="card" aria-labelledby="lead-title">
      <div className="card-head">
        <h2 id="lead-title">Lead qualification</h2>
        {lead && (
          <span className="badge">
            <span className={`dot ${GRADE_DOT[lead.score.grade]}`} />
            {lead.score.grade} lead
          </span>
        )}
      </div>

      {!lead ? (
        <div className="empty">
          <Icon name="user" size={32} />
          <p>The score and sentiment update during a call.</p>
        </div>
      ) : (
        <div className="card-body lead">
          <div className="stack">
            {(identity || lead.returning) && (
              <p className="identity">
                {identity || "Unnamed caller"}
                {lead.returning && <span className="muted"> · returning caller</span>}
              </p>
            )}
            <p className="score">
              <strong>{lead.score.total}</strong>
              <span className="muted">out of 100</span>
            </p>
            <Meter value={lead.score.total} max={100} label="Lead score" />
          </div>

          {lead.follow_up && (
            <div className="notice" role="alert">
              <Icon name="alert" />
              <span>Repeated negative sentiment. A person should follow up.</span>
            </div>
          )}

          <ul className="criteria">
            {CRITERIA.map(({ key, label, max }) => {
              const fact = lead.facts[key];
              return (
                <li key={key}>
                  <div className="row">
                    <span>{label}</span>
                    <span className="value">
                      {lead.score.points[key]} / {max}
                    </span>
                  </div>
                  <Meter value={lead.score.points[key]} max={max} label={`${label} points`} />
                  <p className="fact">
                    {fact ? (
                      <>
                        {fact.detail} <q>{fact.evidence}</q>
                      </>
                    ) : (
                      "Not known yet"
                    )}
                  </p>
                </li>
              );
            })}
          </ul>

          <div className="group">
            <h3>Sentiment by turn</h3>
            {lead.sentiments.length === 0 ? (
              <p className="muted">Waiting for the caller.</p>
            ) : (
              <>
                <div
                  className="timeline"
                  role="img"
                  aria-label={`Sentiment by turn: ${lead.sentiments.join(", ")}`}
                >
                  {lead.sentiments.map((label, i) => (
                    <span key={i} className={label} title={`Turn ${i + 1}: ${label}`} />
                  ))}
                </div>
                <div className="legend">
                  {SENTIMENTS.map(({ key, label, dot }) => (
                    <span key={key}>
                      <i className={`dot ${dot}`} />
                      {label} {lead.sentiments.filter((s) => s === key).length}
                    </span>
                  ))}
                </div>
                {lead.sentiment_reason && (
                  <p className="fact">Latest: {lead.sentiment_reason}</p>
                )}
              </>
            )}
          </div>

          {lead.facts.objections.length > 0 && (
            <div className="group">
              <h3>Objections</h3>
              <ul className="chips">
                {lead.facts.objections.map((objection) => (
                  <li key={objection}>{objection}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
