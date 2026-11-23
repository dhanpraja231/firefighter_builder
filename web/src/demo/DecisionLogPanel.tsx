import type { DecisionLogRow } from "../timeline/replay";

const TYPE_COLOR: Record<string, string> = {
  decide: "#4cc9f0",
  act: "#90be6d",
  request_approval: "#f8961e",
  approval: "#f9c74f",
  world_event: "#f94144",
};

/** What each agent decided and why, newest first. The "visible decisions" requirement. */
export function DecisionLogPanel({ rows }: { rows: DecisionLogRow[] }) {
  const ordered = [...rows].reverse();
  return (
    <div
      style={{
        position: "fixed",
        top: 12,
        right: 12,
        width: 320,
        maxHeight: "72vh",
        overflowY: "auto",
        padding: 10,
        background: "rgba(8,10,16,0.85)",
        border: "1px solid #2a2e3a",
        borderRadius: 8,
        color: "#e7eefc",
        fontFamily: "monospace",
        fontSize: 11,
      }}
    >
      <div style={{ marginBottom: 8, opacity: 0.8 }}>Decision log</div>
      {ordered.length === 0 && <div style={{ opacity: 0.5 }}>No decisions yet.</div>}
      {ordered.map((row) => (
        <div key={row.seq} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: "1px solid #20232c" }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: TYPE_COLOR[row.type] ?? "#e7eefc" }}>
            <span>
              [{row.t_sim.toFixed(1)}s] {row.agentId}
            </span>
            <span style={{ opacity: 0.7 }}>{row.type}</span>
          </div>
          <div style={{ opacity: 0.9 }}>{row.summary}</div>
          {row.reasoning && <div style={{ opacity: 0.6, marginTop: 2 }}>&ldquo;{row.reasoning}&rdquo;</div>}
        </div>
      ))}
    </div>
  );
}
