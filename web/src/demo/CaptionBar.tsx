/**
 * A persistent "what's happening right now" bar across the bottom of the
 * screen -- legible regardless of camera angle or how small a 3D speech
 * bubble reads from a wide shot. `kind: "speak"` is an actual line of
 * dialogue (quoted); `kind: "action"` is the agent's reasoning for what
 * it just did, shown as narration when nobody's mid-line.
 */
export function CaptionBar({
  speaker,
  color,
  line,
  kind,
}: {
  speaker: string;
  color: string;
  line: string;
  kind: "speak" | "action";
}) {
  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        bottom: 22,
        transform: "translateX(-50%)",
        maxWidth: "min(760px, 86vw)",
        padding: "10px 20px",
        borderRadius: 10,
        background: "rgba(5,6,10,0.88)",
        border: `1px solid ${color}`,
        boxShadow: "0 6px 24px rgba(0,0,0,0.5)",
        fontFamily: "monospace",
        textAlign: "center",
        pointerEvents: "none",
      }}
    >
      <div style={{ color, fontSize: 12, fontWeight: 700, letterSpacing: "0.06em", marginBottom: 4 }}>
        {speaker.toUpperCase()}
      </div>
      <div
        style={{
          color: kind === "speak" ? "#f7f1e8" : "#b7bfd4",
          fontSize: kind === "speak" ? 18 : 14,
          fontStyle: kind === "speak" ? "normal" : "italic",
          lineHeight: 1.35,
        }}
      >
        {kind === "speak" ? `"${line}"` : line}
      </div>
    </div>
  );
}
