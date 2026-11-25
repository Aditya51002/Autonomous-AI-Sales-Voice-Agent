"use client";

import { useCall } from "../lib/useCall";
import { agentView, CallPanel } from "./CallPanel";
import { Documents } from "./Documents";
import { Icon } from "./Icons";
import { LatencyPanel, Sources } from "./Insights";
import { LeadPanel } from "./LeadPanel";
import { Transcript } from "./Transcript";

export default function Home() {
  const call = useCall();
  const view = agentView(call.status, call.agentState);

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="logo">
              <Icon name="wave" size={20} />
            </span>
            <div>
              <h1>AI Sales Voice Agent</h1>
              <p>Real-time conversations, grounded answers, live lead qualification</p>
            </div>
          </div>
          <span className="pill">
            <span className={`dot ${call.status === "live" ? "good" : call.status === "connecting" ? "warning" : ""}`} />
            {call.status === "idle" ? "Not in a call" : view.title}
          </span>
        </div>
      </header>

      <main className="shell">
        <div className="column">
          <CallPanel {...call} />
          <Transcript lines={call.lines} />
          <Documents />
        </div>
        <div className="column">
          <LeadPanel lead={call.lead} />
          <Sources sources={call.sources} />
          <LatencyPanel latencies={call.latencies} />
        </div>
      </main>
    </>
  );
}
