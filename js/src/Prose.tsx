import { Fragment, type ReactNode } from "react";

/** Inline `**bold**` only. Everything else is a text node — never HTML. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(<strong key={`${keyPrefix}-b${i++}`}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul"; items: string[] };

/** Split text into paragraphs and `- ` bullet lists. */
export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;
  const flush = () => {
    if (current) blocks.push(current);
    current = null;
  };
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    if (bullet) {
      if (!current || current.kind !== "ul") {
        flush();
        current = { kind: "ul", items: [] };
      }
      current.items.push(bullet[1] ?? "");
    } else if (current && current.kind === "ul") {
      // continuation of the previous bullet
      const lastIdx = current.items.length - 1;
      current.items[lastIdx] = `${current.items[lastIdx] ?? ""} ${line.trim()}`;
    } else {
      if (!current) current = { kind: "p", lines: [] };
      current.lines.push(line.trim());
    }
  }
  flush();
  return blocks;
}

export interface ProseProps {
  text: string;
  className?: string;
}

/** Text-only renderer: paragraphs, `- ` bullets, `**bold**`. Never renders HTML. */
export function Prose({ text, className }: ProseProps) {
  const blocks = parseBlocks(text);
  return (
    <div className={className ?? "askpanel-prose"}>
      {blocks.map((b, i) =>
        b.kind === "ul" ? (
          <ul key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{inline(item, `${i}-${j}`)}</li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            {b.lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 ? <br /> : null}
                {inline(line, `${i}-${j}`)}
              </Fragment>
            ))}
          </p>
        ),
      )}
    </div>
  );
}
