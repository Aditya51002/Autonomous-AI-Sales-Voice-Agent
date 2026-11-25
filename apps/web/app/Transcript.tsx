"use client";

import { useEffect, useRef } from "react";
import type { Line } from "../lib/useCall";
import { Icon } from "./Icons";

export function Transcript({ lines }: { lines: Line[] }) {
  const box = useRef<HTMLDivElement>(null);
  const follow = useRef(true);

  // Keep the newest message in view unless the reader has scrolled up.
  useEffect(() => {
    const element = box.current;
    if (element && follow.current) element.scrollTop = element.scrollHeight;
  }, [lines]);

  return (
    <section className="card" aria-labelledby="transcript-title">
      <div className="card-head">
        <h2 id="transcript-title">Live transcript</h2>
        <span className="muted">{lines.length > 0 && `${lines.length} messages`}</span>
      </div>
      <div
        className="transcript"
        ref={box}
        role="log"
        tabIndex={0}
        aria-labelledby="transcript-title"
        onScroll={(event) => {
          const { scrollHeight, scrollTop, clientHeight } = event.currentTarget;
          follow.current = scrollHeight - scrollTop - clientHeight < 40;
        }}
      >
        {lines.length === 0 && (
          <div className="empty">
            <Icon name="chat" size={32} />
            <p>The conversation appears here once the call starts.</p>
          </div>
        )}
        {lines.map((line) => (
          <div key={line.id} className={`message ${line.speaker}`}>
            <span>{line.speaker === "you" ? "You" : "Agent"}</span>
            <p>{line.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
