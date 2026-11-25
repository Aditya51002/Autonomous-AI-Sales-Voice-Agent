"use client";

import { useEffect, useState } from "react";
import type { CallStatus } from "../lib/useCall";
import { Icon } from "./Icons";

const AGENT_STATES: Record<string, { title: string; hint: string }> = {
  initializing: { title: "Getting ready", hint: "The agent is joining the call." },
  listening: { title: "Listening", hint: "Speak in English, Hindi or Hinglish." },
  thinking: { title: "Thinking", hint: "Preparing an answer." },
  speaking: { title: "Speaking", hint: "You can interrupt at any time." },
};

export function agentView(status: CallStatus, agentState: string) {
  if (status === "idle") {
    return {
      key: "idle",
      title: "Talk to the sales assistant",
      hint: "Ask about products and prices in the language you prefer.",
    };
  }
  if (status === "connecting") {
    return { key: "connecting", title: "Connecting", hint: "Setting up the call." };
  }
  const state = AGENT_STATES[agentState];
  return state
    ? { key: agentState, ...state }
    : { key: "connecting", title: "Waiting for the agent", hint: "This takes a few seconds." };
}

function useElapsed(running: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    setSeconds(0);
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 500);
    return () => clearInterval(timer);
  }, [running]);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

interface Props {
  status: CallStatus;
  agentState: string;
  muted: boolean;
  remembered: boolean;
  error: string;
  start: () => void;
  end: () => void;
  toggleMute: () => void;
  forget: () => void;
}

export function CallPanel(props: Props) {
  const [consent, setConsent] = useState(false);
  const live = props.status === "live";
  const idle = props.status === "idle";
  const view = agentView(props.status, props.agentState);
  const elapsed = useElapsed(live);

  return (
    <section className="card stage" aria-label="Call">
      <div className={`orb ${view.key}`}>
        <Icon name={view.key === "speaking" ? "wave" : props.muted ? "micOff" : "mic"} size={34} />
      </div>

      <div role="status">
        <p className="stage-title">{view.title}</p>
        <p className="muted">{live && props.muted ? "Your microphone is muted." : view.hint}</p>
      </div>
      {live && <p className="timer">{elapsed}</p>}

      {idle && (
        <>
          <div className="languages" aria-label="Supported languages">
            <span className="pill">English</span>
            <span className="pill" lang="hi">
              हिंदी
            </span>
            <span className="pill">Hinglish</span>
          </div>
          <label className="consent">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            I agree to speak with an AI assistant and to have the call transcribed.
          </label>
        </>
      )}

      <div className="stage-controls">
        {idle ? (
          <button className="btn primary" onClick={props.start} disabled={!consent}>
            <Icon name="phone" /> Start call
          </button>
        ) : (
          <>
            <button
              className="btn"
              onClick={props.toggleMute}
              disabled={!live}
              aria-pressed={props.muted}
            >
              <Icon name={props.muted ? "micOff" : "mic"} />
              {props.muted ? "Unmute" : "Mute"}
            </button>
            <button className="btn danger" onClick={props.end}>
              <Icon name="phone" /> End call
            </button>
          </>
        )}
      </div>

      {props.error && (
        <div className="notice" role="alert">
          <Icon name="alert" />
          <span>{props.error}</span>
        </div>
      )}

      {idle && props.remembered && (
        <p className="remembered">
          This browser is remembered from an earlier call.
          <button className="btn small" onClick={props.forget}>
            Forget me and erase my data
          </button>
        </p>
      )}
    </section>
  );
}
