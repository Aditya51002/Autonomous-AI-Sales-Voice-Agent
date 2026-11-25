"use client";

import { Room, RoomEvent, Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type CallStatus = "idle" | "connecting" | "live";

export interface Line {
  id: string;
  speaker: "you" | "agent";
  text: string;
}

export interface Latency {
  id: number;
  role: "user" | "assistant";
  language: string;
  stt_ms?: number;
  end_of_turn_ms?: number;
  llm_first_token_ms?: number;
  tts_first_audio_ms?: number;
  total_ms?: number;
}

export interface Source {
  document: string;
  heading: string;
  score: number;
}

export interface LeadState {
  facts: {
    name: string | null;
    company: string | null;
    need: Fact | null;
    budget: Fact | null;
    authority: Fact | null;
    timeline: Fact | null;
    objections: string[];
  };
  score: {
    total: number;
    grade: "Hot" | "Warm" | "Cold";
    points: Record<Criterion, number>;
    reasons: Record<Criterion, string>;
  };
  sentiments: ("positive" | "neutral" | "negative")[];
  sentiment_reason: string;
  follow_up: boolean;
  returning: boolean;
}

export type Criterion = "need" | "budget" | "authority" | "timeline";

export interface Fact {
  detail: string;
  evidence: string;
}

const LEAD_KEY = "voice-agent-lead-id";

export function useCall() {
  const roomRef = useRef<Room | null>(null);
  const [status, setStatus] = useState<CallStatus>("idle");
  const [agentState, setAgentState] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [latencies, setLatencies] = useState<Latency[]>([]);
  const [sources, setSources] = useState<Source[] | null>(null);
  const [lead, setLead] = useState<LeadState | null>(null);
  const [remembered, setRemembered] = useState(false);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");

  const end = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    await room?.disconnect();
    setStatus("idle");
    setAgentState("");
  }, []);

  const start = useCallback(async () => {
    setStatus("connecting");
    setError("");
    setLines([]);
    setLatencies([]);
    setSources(null);
    setLead(null);
    setMuted(false);
    const room = new Room();
    roomRef.current = room;

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) document.body.appendChild(track.attach());
    });
    room.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((element) => element.remove());
    });
    room.on(RoomEvent.ParticipantAttributesChanged, (changed) => {
      if (changed["lk.agent.state"]) setAgentState(changed["lk.agent.state"]);
    });
    room.on(RoomEvent.DataReceived, (data, _participant, _kind, topic) => {
      if (topic !== "latency" && topic !== "sources" && topic !== "lead") return;
      const entry = JSON.parse(new TextDecoder().decode(data));
      if (topic === "lead") setLead(entry);
      else if (topic === "sources") setSources(entry.sources);
      else setLatencies((all) => [...all, { ...entry, id: all.length }]);
    });
    room.on(RoomEvent.Disconnected, () => {
      if (roomRef.current === room) void end();
    });

    // One handler receives both sides of the transcript. Text for a segment
    // either grows inside one stream or arrives again in a newer stream.
    room.registerTextStreamHandler("lk.transcription", async (reader, sender) => {
      const id = reader.info.attributes?.["lk.segment_id"] ?? reader.info.id;
      const speaker = sender.identity === room.localParticipant.identity ? "you" : "agent";
      let text = "";
      for await (const chunk of reader) {
        text += chunk;
        const line: Line = { id, speaker, text };
        setLines((all) =>
          all.some((l) => l.id === id)
            ? all.map((l) => (l.id === id ? line : l))
            : [...all, line],
        );
      }
    });

    try {
      const response = await fetch(`${API_URL}/calls`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ consent: true, lead_id: localStorage.getItem(LEAD_KEY) }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `The API returned ${response.status}.`);
      }
      const { url, token, lead_id } = await response.json();
      localStorage.setItem(LEAD_KEY, lead_id);
      setRemembered(true);
      await room.connect(url, token);
      await room.startAudio();
      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      setStatus("live");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      await end();
    }
  }, [end]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    await room.localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  }, [muted]);

  const forget = useCallback(async () => {
    const id = localStorage.getItem(LEAD_KEY);
    if (!id) return;
    const response = await fetch(`${API_URL}/leads/${id}`, { method: "DELETE" }).catch(() => null);
    if (!response?.ok) {
      setError("Your data could not be erased. Check that the API is running.");
      return;
    }
    localStorage.removeItem(LEAD_KEY);
    setRemembered(false);
    setLead(null);
    setLines([]);
    setError("");
  }, []);

  useEffect(() => setRemembered(Boolean(localStorage.getItem(LEAD_KEY))), []);
  useEffect(() => () => void roomRef.current?.disconnect(), []);

  return {
    status,
    agentState,
    lines,
    latencies,
    sources,
    lead,
    remembered,
    muted,
    error,
    start,
    end,
    toggleMute,
    forget,
  };
}
