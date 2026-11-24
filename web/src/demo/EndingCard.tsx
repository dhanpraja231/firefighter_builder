import { visualFor } from "../timeline/roster";
import type { TimelineEvent } from "../timeline/schema";

interface Outcome {
  rescued: string[];
  lost: string[];
  trapped: string[];
}

/** Each resident's last reported status, by display name. */
export function outcomeOf(events: TimelineEvent[]): Outcome {
  const last = new Map<string, string>();
  for (const e of events) {
    if (e.type === "status" && e.agent_role === "victim" && e.payload.victim_status) {
      last.set(e.agent_id, e.payload.victim_status);
    }
  }
  const names = (wanted: (s: string) => boolean) =>
    [...last.entries()].filter(([, s]) => wanted(s)).map(([id]) => visualFor(id, "victim").label);
  return {
    rescued: names((s) => s === "rescued"),
    lost: names((s) => s === "lost"),
    trapped: names((s) => s !== "rescued" && s !== "lost"),
  };
}

function humanize(ending: string): string {
  const text = ending.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Shown when a story finishes: how it ended, who made it out, and a way to start a different one. */
export function EndingCard({
  ending,
  events,
  onAgain,
}: {
  ending?: string;
  events: TimelineEvent[];
  onAgain: () => void;
}) {
  const { rescued, lost, trapped } = outcomeOf(events);
  const line = (label: string, names: string[], color: string) =>
    names.length > 0 && (
      <div style={{ marginTop: 8, fontSize: 13 }}>
        <span style={{ color, fontWeight: 700 }}>
          {label} ({names.length}):
        </span>{" "}
        <span style={{ opacity: 0.9 }}>{names.join(", ")}</span>
      </div>
    );
  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        top: "42%",
        transform: "translate(-50%, -50%)",
        width: "min(520px, 86vw)",
        padding: "22px 26px",
        background: "rgba(6,8,14,0.92)",
        border: "1px solid #ffd166",
        borderRadius: 10,
        color: "#e7eefc",
        fontFamily: "monospace",
        textAlign: "center",
        boxShadow: "0 0 40px rgba(255,209,102,0.25)",
      }}
    >
      <div style={{ fontSize: 11, letterSpacing: 3, color: "#ffd166", opacity: 0.85 }}>THE END</div>
      <div style={{ fontSize: 22, fontWeight: 700, margin: "8px 0 4px" }}>{ending ? humanize(ending) : "Story complete"}</div>
      {line("Made it out", rescued, "#90be6d")}
      {line("Lost", lost, "#f94144")}
      {line("Still inside", trapped, "#f8961e")}
      <button
        onClick={onAgain}
        style={{
          marginTop: 18,
          padding: "9px 16px",
          fontSize: 13,
          fontFamily: "monospace",
          background: "#2a4a3a",
          color: "#e7eefc",
          border: "1px solid #39415a",
          borderRadius: 4,
          cursor: "pointer",
        }}
      >
        ▶ Watch a different story
      </button>
    </div>
  );
}
