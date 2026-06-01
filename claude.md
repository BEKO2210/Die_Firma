# Arbeitsvereinbarung für dieses Projekt (verbindlich)

Befolge diese Regeln in JEDEM Projekt, unabhängig von Sprache/Framework.
Sie fassen wiederkehrende Fehlerquellen zusammen, die vermieden werden müssen.

## 1. Abhängigkeiten & Sicherheit (von Tag 1)
- Beim Setup IMMER die **neueste stabile** Version jeder Hauptabhängigkeit wählen
  und das Datum/den Stand notieren. Keine Versionen aus dem Gedächtnis raten.
- Vor jedem Dependency-Bump die **peerDependencies** prüfen (`npm view <pkg> peerDependencies`)
  und entscheiden, ob ein Minor-/Patch- statt eines Major-Bumps reicht.
- **Major-Upgrades nur bewusst:** zuerst den offiziellen Migration-Guide lesen,
  Breaking Changes auflisten, dann migrieren. Niemals blind auf 'latest' springen.
- `npm audit` (bzw. Äquivalent) als **CI-Gate** einbauen (`--audit-level=high`),
  zusätzlich Dependabot/Renovate aktivieren. Ziel: dauerhaft 0 High/Critical.
- Transitive Schwachstellen über `overrides`/`resolutions` lösen, Lockfile
  danach neu generieren — niemals von Hand editieren.

## 2. Branch- & PR-Hygiene
- Jeden Branch IMMER von der **aktuellen** `main` abzweigen (`git fetch` zuerst),
  nicht von einem veralteten Stand. Vor dem Push rebasen/mergen, wenn `main` lief.
- **Ein PR = ein Anliegen.** Doku, Feature, Security, Dependency-Bump trennen.
- **Lockfiles (package-lock.json o. ä.) bei Konflikten NIE im Web-Editor von Hand
  auflösen** — `--theirs/--ours` wählen und `install` neu laufen lassen.
- Bei abhängigen PRs die Reihenfolge explizit dokumentieren (welcher zuerst).
- Vor jedem Push lokal den **kompletten CI-Satz grün** haben. Nie rot pushen.

## 3. Verifikation statt Behauptung
- Bei Bugs/Fehlern: **zuerst reproduzieren**, Ursache bestätigen, DANN fixen.
  Nicht raten und nicht 'müsste jetzt gehen' schreiben.
- Tests NIE abschwächen, skippen oder Assertions aufweichen, um grün zu werden.
- Nach JEDER Code-Änderung vor dem Testen/Screenshoten **neu bauen** — niemals
  gegen einen veralteten Build ('stale build') testen.
- Ergebnisse ehrlich berichten: fehlgeschlagen ist fehlgeschlagen, mit Ausgabe.

## 4. Test- & Qualitäts-Setup (von Anfang an, nicht nachträglich)
- Strikte Typprüfung (`strict` + `noUncheckedIndexedAccess` o. ä.) ab Commit 1.
- Coverage-Gate auf dem **sicherheits-/logikkritischen Kern** (Ziel 100 %),
  ergänzt durch **Mutation-Testing** als echtes Qualitätsmaß.
- **End-to-End-Tests mit echten Flows** (echte Krypto/echter Browser), nicht nur Mocks.
- Bei UI: **Barrierefreiheit automatisiert** prüfen (axe/WCAG-Gate in CI) —
  Kontraste/Labels/Sprungmarken nicht raten, sondern messen.
- Lint **und** Format-Check im CI.

## 5. Deterministische Skripte & Automatisierung
- Test-/Screenshot-/Seed-Skripte müssen **reproduzierbar** sein: DB vor jedem Lauf
  zurücksetzen + frisch seeden, keine Abhängigkeit von Vorlauf-Zustand.
- **Stabile Selektoren** verwenden (Rollen/IDs, `exact: true`), keine mehrdeutigen
  Text-Treffer; auf konkrete Navigation/URL warten statt auf generische Begriffe.
- Reihenfolge beachten: Werte (z. B. Tokens) **vor** dem Maskieren/Transformieren
  auslesen. Browser-Autofill in Formularfeldern aktiv neutralisieren.
- Hintergrunddienste sauber starten/stoppen (Ports freigeben), keine Zombie-Prozesse.

## 6. Konfigurations- & Secret-Härtung (sofort, nicht 'später')
- **Keine funktionierenden Default-Secrets.** Bekannte Platzhalter
  ('changeme', 'bitte-ersetzen', …) hart ablehnen → Start bricht ab.
- Secrets nur aus Umgebung, mit Mindest-Entropie-/Format-Check beim Start.
- Vom Client kontrollierbare Header (z. B. `X-Forwarded-For`) **nur hinter einem
  ausdrücklich vertrauenswürdigen Proxy** auswerten (Flag), sonst ignorieren.
- Dienste/Ports standardmäßig an `127.0.0.1` binden, nicht an `0.0.0.0`.
- Trennung Dev-/Prod-Konfiguration; Prod-Compose ohne offene DB-Ports.

## 7. Ehrliche Kommunikation & Dokumentation
- Sicherheitsversprechen präzise: nur belegbare Aussagen (z. B. 'verschlüsselt,
  aber NICHT extern auditiert' statt 'Zero-Knowledge').
- README/Doku immer am **tatsächlichen Code-Stand** halten (Versionen, Test-Zahlen,
  Feature-Status) — keine veralteten Badges/Claims.
- Bei sicherheits-/architekturkritischer Mehrdeutigkeit **nachfragen statt raten**.

## 8. Definition of Done (vor 'fertig')
[ ] Neueste stabile Deps, `audit` sauber, Lockfile konsistent
[ ] Lint + Typecheck + Unit (Coverage-Gate) + E2E + (a11y) + Build lokal grün
[ ] Frisch gebaut und gegen den neuen Build verifiziert
[ ] Branch von aktueller main, Konflikte sauber gelöst, fokussierter PR
[ ] Doku/Changelog aktualisiert, Aussagen belegt
