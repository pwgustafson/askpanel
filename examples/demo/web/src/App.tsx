import { useState } from "react";
import { AskPanel } from "@askpanel/react";
import "@askpanel/react/styles.css";

const TABS = ["Albums", "People", "Sharing", "Settings"] as const;

export function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Albums");
  const [open, setOpen] = useState(false);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "40px auto", padding: "0 16px" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>Orchard</h1>
        <nav style={{ display: "flex", gap: 8 }}>
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: "6px 12px",
                borderRadius: 8,
                border: "1px solid #ddd",
                background: t === tab ? "#e8effc" : "white",
                cursor: "pointer",
              }}
            >
              {t}
            </button>
          ))}
        </nav>
        <button
          onClick={() => setOpen(true)}
          aria-label="Help"
          title="Help"
          style={{ marginLeft: "auto", width: 36, height: 36, borderRadius: 18, border: "1px solid #ddd", cursor: "pointer" }}
        >
          ?
        </button>
      </header>

      <main style={{ marginTop: 32, color: "#444" }}>
        <h2 style={{ fontSize: 18 }}>{tab}</h2>
        <p>
          This is a stand-in for the <strong>{tab}</strong> screen of an imaginary family photo app. Press{" "}
          <strong>?</strong> to open the help panel. The panel tells the server which tab you are on, so
          starter questions and answers can match the screen.
        </p>
        <p>
          Try: <em>"How do I share an album with my parents?"</em>, <em>"Why can't I find my dog photos?"</em>,
          or request a feature and watch the interview turn into a summary you can send.
        </p>
      </main>

      <AskPanel
        base="/api/askpanel"
        open={open}
        onOpenChange={setOpen}
        getContext={() => tab}
        entries={["help", "feature", "bug"]}
      />
    </div>
  );
}
