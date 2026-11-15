type SymbolName = "available" | "failed" | "unavailable" | "play" | "pause";

/** Shared optical size and stroke weight for recorded states and replay controls. */
export function WorkspaceIcon({ name }: {name: SymbolName}) {
  return <svg key={name} className="workspace-icon" width="18" height="18" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "available" ? <path d="m5 12 4 4L19 6" />
      : name === "failed" ? <path d="m7 7 10 10M17 7 7 17" />
      : name === "unavailable" ? <path d="M5 12h14" />
      : name === "play" ? <path d="m9 5 10 7-10 7Z" />
      : <path d="M8 5v14M16 5v14" />}
  </svg>;
}
