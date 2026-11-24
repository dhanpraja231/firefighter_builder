import type { DecisionLogRow } from "../timeline/replay";
import { visualFor } from "../timeline/roster";

const pretty = (id: string) => id.replace(/^(robot|ladder|spray|vent):/, (_, k) => ({ robot: "rescue-1 → ", ladder: "ladder → ", spray: "spray ", vent: "vent floor " }[k as string] ?? ""))
  .replace(/victim-/g, "").replace(/_/g, " ");

/**
 * What each agent decided and why, newest on top. Only real decisions (and human verdicts and
 * twists) -- not every fire/smoke update -- with the options the agent turned down.
 */
export function DecisionLogPanel({ rows }: { rows: DecisionLogRow[] }) {
  const ordered = [...rows].reverse().slice(0, 7);
  const decisions = rows.filter((r) => r.type !== "world_event" && r.type !== "approval").length;
  return (
    <div style={{
      position: "fixed", top: 12, right: 12, width: 360, maxHeight: "calc(100vh - 90px)", overflow: "hidden",
      background: "rgba(9,11,17,0.88)", border: "1px solid #262b38", borderRadius: 10, color: "#eef2fb",
      fontFamily: "'IBM Plex Sans', system-ui, sans-serif", fontSize: 12.5, lineHeight: 1.45,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "10px 14px 8px", borderBottom: "1px solid #20242f" }}>
        <span style={{ fontWeight: 600, fontSize: 13 }}>Agent decisions</span>
        <span style={{ opacity: 0.6, fontSize: 11.5 }}>{decisions} so far</span>
      </div>
      {ordered.length === 0 && <div style={{ padding: 14, opacity: 0.55 }}>Waiting for the first decision.</div>}
      {ordered.map((row, i) => {
        const v = visualFor(row.agentId, row.role);
        const isTwist = row.type === "world_event";
        const isVerdict = row.type === "approval";
        const rejected = (row.options ?? []).filter((o) => o !== row.choice);
        return (
          <div key={row.seq} style={{
            padding: "9px 14px 10px", borderBottom: "1px solid #1b1f29",
            background: i === 0 ? "rgba(255,255,255,0.06)" : "transparent", opacity: i === 0 ? 1 : Math.max(0.45, 0.9 - i * 0.08),
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: 4, background: isTwist ? "#f25f3a" : v.color, flex: "none" }} />
              <span style={{ fontWeight: 600 }}>{isTwist ? "Twist" : v.label}</span>
              <span style={{ marginLeft: "auto", fontFamily: "monospace", fontSize: 11, opacity: 0.55 }}>{row.t_sim.toFixed(1)}s</span>
            </div>
            <div style={{ marginTop: 3, fontWeight: 500, color: isTwist ? "#ffb199" : "#ffffff" }}>
              {isTwist ? (row.twist ?? "").replace(/-/g, " ")
                : isVerdict ? `Human: ${row.summary.replace("approval: ", "")}`
                : row.choice ? `Chose ${pretty(row.choice)}` : row.summary}
            </div>
            {rejected.length > 0 && (
              <div style={{ marginTop: 2, fontSize: 11.5, opacity: 0.55 }}>
                over {rejected.slice(0, 3).map(pretty).join(", ")}{rejected.length > 3 ? ` +${rejected.length - 3}` : ""}
              </div>
            )}
            {row.reasoning && <div style={{ marginTop: 4, opacity: 0.8 }}>{row.reasoning}</div>}
            {row.latencyMs != null && (
              <div style={{ marginTop: 4, fontFamily: "monospace", fontSize: 10.5, opacity: 0.45 }}>
                {(row.model ?? "").replace(/^.*:/, "")} · {(row.latencyMs / 1000).toFixed(1)} s
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
