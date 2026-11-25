import type { Criterion, LeadState } from "../lib/useCall";

const CRITERIA: { key: Criterion; label: string; max: number }[] = [
  { key: "need", label: "Need", max: 30 },
  { key: "budget", label: "Budget", max: 25 },
  { key: "authority", label: "Authority", max: 20 },
  { key: "timeline", label: "Timeline", max: 25 },
];

const MOOD = { positive: "🙂", neutral: "😐", negative: "🙁" };

export function LeadPanel({ lead }: { lead: LeadState | null }) {
  return (
    <section aria-label="Lead">
      <h2>Lead qualification</h2>
      {!lead && <p className="empty">The score and sentiment update during a call.</p>}
      {lead && (
        <>
          <p>
            <strong>
              {lead.score.grade}: {lead.score.total} / 100
            </strong>
            {lead.returning && " · returning caller"}
            {(lead.facts.name || lead.facts.company) &&
              ` · ${[lead.facts.name, lead.facts.company].filter(Boolean).join(", ")}`}
          </p>
          {lead.follow_up && (
            <p role="alert">Repeated negative sentiment: a person should follow up.</p>
          )}
          <div className="table">
            <table>
              <thead>
                <tr>
                  <th>Criterion</th>
                  <th>Points</th>
                  <th>What was said</th>
                </tr>
              </thead>
              <tbody>
                {CRITERIA.map(({ key, label, max }) => {
                  const fact = lead.facts[key];
                  return (
                    <tr key={key}>
                      <td>{label}</td>
                      <td>
                        {lead.score.points[key]} / {max}
                      </td>
                      <td>
                        {fact ? `${fact.detail} (“${fact.evidence}”)` : lead.score.reasons[key]}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p>
            Sentiment:{" "}
            {lead.sentiments.length === 0
              ? "waiting for the caller"
              : lead.sentiments.map((label, i) => (
                  <span key={i} role="img" aria-label={label} title={label}>
                    {MOOD[label]}
                  </span>
                ))}
            {lead.sentiment_reason && ` (latest: ${lead.sentiment_reason})`}
          </p>
          {lead.facts.objections.length > 0 && (
            <p>Objections: {lead.facts.objections.join("; ")}</p>
          )}
        </>
      )}
    </section>
  );
}
