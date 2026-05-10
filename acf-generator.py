#!/usr/bin/env python3
"""
Steam ACF Generator
====================
Durchsucht die Festplatte nach steamapps/common Ordnern,
ermittelt App-IDs über die Steam Store API (kein Browser nötig)
und schreibt korrekte appmanifest_XXXX.acf Dateien.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ── Farben ──────────────────────────────────────────────────────────────
G  = "\033[92m"  # grün
Y  = "\033[93m"  # gelb
R  = "\033[91m"  # rot
B  = "\033[94m"  # blau
C  = "\033[96m"  # cyan
W  = "\033[1m"   # fett
RS = "\033[0m"   # reset


# ── Steam Store API ──────────────────────────────────────────────────────

def search_steam_appid(game_name: str) -> tuple[int | None, str | None]:
    """
    Sucht auf der Steam Store API nach dem Spielnamen.
    Gibt (appid, offizieller_name) zurück oder (None, None).
    """
    encoded = urllib.parse.quote(game_name)
    url = (
        f"https://store.steampowered.com/api/storesearch/"
        f"?term={encoded}&l=english&cc=DE"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        items = data.get("items", [])
        if not items:
            return None, None
        # Bestes Ergebnis: exakter Namens-Match bevorzugt
        for item in items:
            if item.get("name", "").lower() == game_name.lower():
                return item["id"], item["name"]
        # Sonst einfach erstes Ergebnis
        best = items[0]
        return best["id"], best["name"]
    except Exception as e:
        print(f"  {R}API-Fehler für '{game_name}': {e}{RS}")
        return None, None


def get_app_details(appid: int) -> dict:
    """Holt Detailinfos (Name, Typ) für eine App-ID."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        entry = data.get(str(appid), {})
        if entry.get("success"):
            return entry.get("data", {})
    except Exception:
        pass
    return {}


# ── ACF-Datei schreiben ──────────────────────────────────────────────────

ACF_TEMPLATE = """\
"AppState"
{{
\t"appid"\t\t"{appid}"
\t"Universe"\t\t"1"
\t"name"\t\t"{name}"
\t"StateFlags"\t\t"4"
\t"installdir"\t\t"{installdir}"
\t"LastUpdated"\t\t"{timestamp}"
\t"UpdateResult"\t\t"0"
\t"SizeOnDisk"\t\t"0"
\t"buildid"\t\t"0"
\t"LastOwner"\t\t"0"
\t"BytesToDownload"\t\t"0"
\t"BytesDownloaded"\t\t"0"
\t"BytesToStage"\t\t"0"
\t"BytesStaged"\t\t"0"
\t"TargetBuildID"\t\t"0"
\t"AutoUpdateBehavior"\t\t"0"
\t"AllowOtherDownloadsWhileRunning"\t\t"0"
\t"ScheduledAutoUpdate"\t\t"0"
\t"InstalledDepots"\t\t{{}}
\t"SharedDepots"\t\t{{}}
\t"UserConfig"\t\t{{}}
\t"MountedConfig"\t\t{{}}
}}
"""


def write_acf(steamapps_dir: Path, appid: int, name: str, installdir: str) -> Path:
    acf_path = steamapps_dir / f"appmanifest_{appid}.acf"
    content = ACF_TEMPLATE.format(
        appid=appid,
        name=name,
        installdir=installdir,
        timestamp=int(time.time()),
    )
    acf_path.write_text(content, encoding="utf-8")
    return acf_path


# ── Filesystem-Scan ──────────────────────────────────────────────────────

SKIP_DIRS = {
    "/proc", "/sys", "/dev", "/run", "/snap",
    "/boot", "/lost+found",
}


def find_steamapps_common_dirs(roots: list[str]) -> list[Path]:
    """
    Durchsucht alle angegebenen Wurzel-Pfade nach Ordnern
    mit dem Muster …/steamapps/common
    """
    found = []
    for root in roots:
        print(f"\n{B}🔍 Durchsuche: {root}{RS}")
        for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
            p = Path(dirpath)

            # Blacklist: Systemordner überspringen
            if any(str(p).startswith(s) for s in SKIP_DIRS):
                dirnames.clear()
                continue

            # Versteckte Ordner und bestimmte Pfade ignorieren
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".")
                and d not in {"proc", "sys", "dev"}
            ]

            if p.name == "common" and p.parent.name == "steamapps":
                print(f"  {G}✔ Gefunden: {p}{RS}")
                found.append(p)
                dirnames.clear()   # nicht tiefer gehen

    return found


def get_scan_roots() -> list[str]:
    """
    Bestimmt, welche Verzeichnisse gescannt werden sollen.
    Bevorzugt gemountete Laufwerke + Home.
    """
    roots = ["/home", "/mnt", "/media", "/run/media"]
    # Auch das Root-Filesystem, aber nur eine Ebene
    for entry in Path("/").iterdir():
        s = str(entry)
        if s not in SKIP_DIRS and s not in roots and entry.is_dir():
            # Nur wenn es kein Symlink ist und kein Systemordner
            if not entry.is_symlink() and entry.name not in {
                "proc", "sys", "dev", "run", "snap", "boot",
                "lost+found", "bin", "sbin", "lib", "lib64",
                "usr", "etc", "var", "tmp",
            }:
                roots.append(s)
    return roots


# ── Hauptprogramm ────────────────────────────────────────────────────────

def main():
    print(f"\n{W}{'='*60}")
    print("  Steam ACF Generator")
    print(f"{'='*60}{RS}\n")

    # 1) Scan-Pfade bestimmen
    roots = get_scan_roots()
    print(f"{C}Scan-Wurzeln: {', '.join(roots)}{RS}")

    # Optional: Nutzer kann eigene Pfade übergeben
    if len(sys.argv) > 1:
        roots = sys.argv[1:]
        print(f"{Y}Nutze angegebene Pfade: {roots}{RS}")

    # 2) steamapps/common Ordner finden
    common_dirs = find_steamapps_common_dirs(roots)

    if not common_dirs:
        print(f"\n{R}Keine steamapps/common Ordner gefunden.{RS}")
        print("Tipp: Gib den Pfad als Argument an:")
        print("  python3 steam_acf_generator.py /4BTRFS")
        sys.exit(1)

    print(f"\n{G}✔ {len(common_dirs)} steamapps/common Ordner gefunden.{RS}\n")

    # 3) Für jeden gefundenen common-Ordner
    total_written = 0
    total_skipped = 0
    total_notfound = 0

    for common_dir in common_dirs:
        steamapps_dir = common_dir.parent
        print(f"\n{W}{'─'*60}")
        print(f"  Bibliothek: {steamapps_dir}")
        print(f"{'─'*60}{RS}")

        # Alle Unterordner = installierte Spiele
        game_folders = sorted([
            d for d in common_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

        if not game_folders:
            print(f"  {Y}Keine Spiele-Ordner gefunden.{RS}")
            continue

        print(f"  {len(game_folders)} Spiele-Ordner gefunden.\n")

        for game_dir in game_folders:
            folder_name = game_dir.name
            print(f"  {C}🎮 {folder_name}{RS}", end=" ", flush=True)

            # Prüfen ob ACF schon existiert (mit passender installdir)
            existing_acf = list(steamapps_dir.glob("appmanifest_*.acf"))
            already_exists = False
            for acf in existing_acf:
                try:
                    content = acf.read_text(encoding="utf-8", errors="ignore")
                    if f'"{folder_name}"' in content:
                        already_exists = True
                        break
                except Exception:
                    pass

            if already_exists:
                print(f"→ {Y}ACF existiert bereits, übersprungen.{RS}")
                total_skipped += 1
                continue

            # Steam API abfragen
            appid, official_name = search_steam_appid(folder_name)
            time.sleep(0.5)  # Rate-Limit respektieren

            if appid is None:
                print(f"→ {R}Nicht gefunden auf Steam.{RS}")
                total_notfound += 1
                continue

            # ACF schreiben
            acf_path = write_acf(steamapps_dir, appid, official_name, folder_name)
            print(f"→ {G}✔ ID {appid} → {acf_path.name}{RS}")
            print(f"    Name: {official_name}")
            total_written += 1

    # 4) Zusammenfassung
    print(f"\n{W}{'='*60}")
    print("  Fertig!")
    print(f"{'='*60}{RS}")
    print(f"  {G}✔ Geschrieben:       {total_written}{RS}")
    print(f"  {Y}⟳ Bereits vorhanden: {total_skipped}{RS}")
    print(f"  {R}✗ Nicht gefunden:    {total_notfound}{RS}\n")

    if total_notfound > 0:
        print(f"{Y}Tipp: Nicht gefundene Spiele haben oft leicht abweichende")
        print(f"Ordnernamen. Du kannst die ID manuell auf:")
        print(f"  https://www.steamidfinder.com/")
        print(f"oder https://steamdb.info/ suchen und dann")
        print(f"das Script mit dem korrekten Namen erneut aufrufen.{RS}\n")


if __name__ == "__main__":
    main()
