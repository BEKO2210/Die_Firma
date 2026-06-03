// Dashboard internationalisation (review §5). Flat message catalogues per
// language with an English fallback; the active language comes from the
// DIE_FIRMA_LANG env var (default "de" to preserve the current UI). The same
// resolved catalogue is sent to the browser via the bootstrap payload so the
// client-rendered labels are localised too.

export type Lang = "de" | "en";
export const LANGS: readonly Lang[] = ["de", "en"];
export const DEFAULT_LANG: Lang = "de";

type Catalogue = Record<string, string>;

const EN: Catalogue = {
  "app.subtitle": "autonomous digital agency — submit jobs & follow live",
  "conn.polling": "polling",
  "form.newJob": "New job",
  "form.title": "Title",
  "form.titlePlaceholder": "e.g. Write a Python function that reverses a string",
  "form.description": "Description",
  "form.optional": "(optional)",
  "form.descPlaceholder": "More detail about the task — empty = the title is used",
  "form.type": "Type",
  "form.priority": "Priority",
  "form.prio1": "1 (high · approval required)",
  "form.prio2": "2 (normal)",
  "form.prio3": "3 (low)",
  "form.deliverable": "Deliverable",
  "form.verify": "Verify command",
  "form.verifyPlaceholder": "e.g. ls *.txt",
  "form.requireApproval": "Require manual approval",
  "form.submit": "Submit job",
  "kanban.title": "Kanban",
  "kanban.queue": "Queue",
  "kanban.progress": "In Progress",
  "kanban.review": "Review",
  "kanban.done": "Done",
  "agents.title": "Agent monitor",
  "agents.legend":
    "Colour = agent · “working” = activity in the last 12 s · bar = token share relative to the busiest agent · text = current action",
  "panel.terminalChat": "Terminal and chat",
  "tabs.view": "View",
  "tab.terminal": "Live terminal",
  "tab.chat": "Chat",
  "terminal.stream": "Telemetry stream",
  "chat.model": "Model",
  "chat.jobContext": "Job context",
  "chat.log": "Chat history",
  "chat.inputPlaceholder": "Ask the LLM about your deliverables …",
  "chat.message": "Message",
  "chat.send": "Send",
  "chat.copy": "Copy",
  "chat.copied": "Copied",
  "chat.empty": "Ask a question about your deliverables.",
  "form.loadExample": "Load example",
  "metrics.bar": "Live metrics",
  "metric.tokensPerSec": "Tokens/s",
  "metric.eventsPerSec": "Events/s",
  "metric.activeTasks": "Active tasks",
  "metric.tokensToday": "Tokens today",
  "metric.totalTasks": "Total tasks",
  "metric.failedToday": "Failed today",
  "metric.window": "{n}s window",
  "metric.done": "{n} done",
  "metric.failed": "failed",
  "metric.running": "running …",
  "metric.quiet": "quiet",
  "metric.noActivity": "⚠ {n}s no activity",
  "agent.working": "working",
  "agent.ready": "ready",
  "agent.runningShort": "running …",
  "agent.tasks": "Tasks",
  "agent.tokenShare": "{p}% of all token work ({n} tokens)",
  "agent.noTokensYet": "working — no tokens measured yet",
  "agent.noTokenWork": "no token work",
  "term.idle": "idle",
  "card.untitled": "(untitled)",
  "card.approve": "Approve",
  "kanban.empty": "empty",
  "role.dispatcher": "Planning",
  "role.worker": "Execution",
  "role.reviewer": "Review",
  "role.sentinel": "Sentinel",
  "theme.toggle": "Toggle light/dark theme",
  "toast.dismiss": "Dismiss",
  "error.generic": "Error",
  "error.network": "Network error",
  "error.jobFailed": "Could not submit job",
  "error.approveFailed": "Approval failed",
  "error.chatFailed": "Chat failed",
  "error.copyFailed": "Copy to clipboard failed",
};

const DE: Catalogue = {
  "app.subtitle": "autonome digitale Agentur — Aufträge aufgeben & live verfolgen",
  "conn.polling": "polling",
  "form.newJob": "Neuer Auftrag",
  "form.title": "Titel",
  "form.titlePlaceholder": "z. B. Schreibe eine Python-Funktion, die einen String umkehrt",
  "form.description": "Beschreibung",
  "form.optional": "(optional)",
  "form.descPlaceholder": "Mehr Details zur Aufgabe — bleibt leer = Titel wird verwendet",
  "form.type": "Typ",
  "form.priority": "Priorität",
  "form.prio1": "1 (hoch · Freigabe nötig)",
  "form.prio2": "2 (normal)",
  "form.prio3": "3 (niedrig)",
  "form.deliverable": "Lieferform",
  "form.verify": "Verify-Kommando",
  "form.verifyPlaceholder": "z. B. ls *.txt",
  "form.requireApproval": "Manuelle Freigabe verlangen",
  "form.submit": "Auftrag aufgeben",
  "kanban.title": "Kanban",
  "kanban.queue": "Queue",
  "kanban.progress": "In Progress",
  "kanban.review": "Review",
  "kanban.done": "Done",
  "agents.title": "Agenten-Monitor",
  "agents.legend":
    "Farbe = Agent · „arbeitet“ = Aktivität in den letzten 12 s · Balken = Tokenanteil relativ zum aktivsten Agenten · Text = aktuelle Aktion",
  "panel.terminalChat": "Terminal und Chat",
  "tabs.view": "Ansicht",
  "tab.terminal": "Live-Terminal",
  "tab.chat": "Chat",
  "terminal.stream": "Telemetrie-Stream",
  "chat.model": "Modell",
  "chat.jobContext": "Job-Kontext",
  "chat.log": "Chatverlauf",
  "chat.inputPlaceholder": "Frag die LLM etwas zu deinen Deliverables …",
  "chat.message": "Nachricht",
  "chat.send": "Senden",
  "chat.copy": "Kopieren",
  "chat.copied": "Kopiert",
  "chat.empty": "Stelle eine Frage zu deinen Deliverables.",
  "form.loadExample": "Beispiel laden",
  "metrics.bar": "Live-Metriken",
  "metric.tokensPerSec": "Tokens/s",
  "metric.eventsPerSec": "Events/s",
  "metric.activeTasks": "Aktive Tasks",
  "metric.tokensToday": "Tokens heute",
  "metric.totalTasks": "Tasks gesamt",
  "metric.failedToday": "Failed heute",
  "metric.window": "{n}s Fenster",
  "metric.done": "{n} fertig",
  "metric.failed": "fehlgeschlagen",
  "metric.running": "läuft …",
  "metric.quiet": "ruhig",
  "metric.noActivity": "⚠ {n}s keine Aktivität",
  "agent.working": "arbeitet",
  "agent.ready": "bereit",
  "agent.runningShort": "läuft …",
  "agent.tasks": "Tasks",
  "agent.tokenShare": "{p}% der gesamten Token-Arbeit ({n} Tokens)",
  "agent.noTokensYet": "arbeitet — noch keine Tokens gemessen",
  "agent.noTokenWork": "keine Token-Arbeit",
  "term.idle": "idle",
  "card.untitled": "(ohne Titel)",
  "card.approve": "Freigeben",
  "kanban.empty": "leer",
  "role.dispatcher": "Planung",
  "role.worker": "Ausführung",
  "role.reviewer": "Review",
  "role.sentinel": "Wächter",
  "theme.toggle": "Hell/Dunkel umschalten",
  "toast.dismiss": "Schließen",
  "error.generic": "Fehler",
  "error.network": "Netzwerkfehler",
  "error.jobFailed": "Auftrag konnte nicht gesendet werden",
  "error.approveFailed": "Freigabe fehlgeschlagen",
  "error.chatFailed": "Chat fehlgeschlagen",
  "error.copyFailed": "Kopieren fehlgeschlagen",
};

const CATALOGUES: Record<Lang, Catalogue> = { en: EN, de: DE };

/** Resolve the active language from the environment (default "de"). */
export function getLang(): Lang {
  const raw = (process.env.DIE_FIRMA_LANG ?? "").toLowerCase();
  return (LANGS as readonly string[]).includes(raw) ? (raw as Lang) : DEFAULT_LANG;
}

/** The catalogue for `lang`, merged over the English fallback. */
export function messages(lang: Lang): Catalogue {
  return { ...EN, ...CATALOGUES[lang] };
}

/** Interpolate `{name}` placeholders in a template. */
export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_m, k: string) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  );
}

/** A translator bound to `lang`: key -> formatted string (falls back to key). */
export function createT(lang: Lang): (key: string, vars?: Record<string, string | number>) => string {
  const cat = messages(lang);
  return (key, vars) => interpolate(cat[key] ?? key, vars);
}
