#!/usr/bin/env python3
"""
Steam ACF Generator
====================
Scans the filesystem for steamapps/common folders,
looks up App IDs via the Steam Store API (no browser needed),
and writes correct appmanifest_XXXX.acf files.
"""

import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ── Colors ──────────────────────────────────────────────────────────────
G  = "\033[92m"
Y  = "\033[93m"
R  = "\033[91m"
B  = "\033[94m"
C  = "\033[96m"
W  = "\033[1m"
RS = "\033[0m"


# ── Name normalization helpers ───────────────────────────────────────────

def folder_to_search_variants(folder_name: str) -> list[str]:
    """
    Generates multiple search query variants from a folder name.
    Tries increasingly aggressive transformations to maximize match rate.
    """
    variants = []

    # 1) Raw folder name as-is
    variants.append(folder_name)

    # 2) Replace underscores / hyphens with spaces
    spaced = re.sub(r"[_\-]+", " ", folder_name).strip()
    if spaced != folder_name:
        variants.append(spaced)

    # 3) Insert spaces before capital letters (CamelCase -> Camel Case)
    camel = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", spaced)
    if camel != spaced:
        variants.append(camel)

    # 4) Strip trailing version numbers / roman numerals / years
    stripped = re.sub(
        r"\s*[\(\[]?v?\d+(\.\d+)*[\)\]]?\s*$", "", camel, flags=re.IGNORECASE
    ).strip()
    if stripped and stripped != camel:
        variants.append(stripped)

    # 5) Strip common suffixes (Demo, Beta, Alpha, Prologue, Definitive Edition, etc.)
    suffixes = [
        r"\s*[-–]?\s*(Demo|Beta|Alpha|Prologue|Preview|Early.Access)$",
        r"\s*:?\s*(Definitive|Complete|Enhanced|Remastered|GOTY|Gold)\s+Edition$",
        r"\s*[\(\[].*?[\)\]]$",   # anything in brackets
    ]
    base = camel
    for pat in suffixes:
        trimmed = re.sub(pat, "", base, flags=re.IGNORECASE).strip()
        if trimmed and trimmed != base:
            variants.append(trimmed)
            base = trimmed

    # 6) Only first two words (for very long names)
    words = camel.split()
    if len(words) > 2:
        variants.append(" ".join(words[:2]))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for v in variants:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def similarity_score(a: str, b: str) -> float:
    """
    Token-based similarity: fraction of words in `a` that appear in `b`.
    """
    a_tokens = set(re.findall(r"\w+", a.lower()))
    b_tokens = set(re.findall(r"\w+", b.lower()))
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens)


# ── Steam Store API ──────────────────────────────────────────────────────

def _steam_search(query: str) -> list[dict]:
    """Raw call to Steam store search API."""
    encoded = urllib.parse.quote(query)
    url = (
        f"https://store.steampowered.com/api/storesearch/"
        f"?term={encoded}&l=english&cc=US"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        return data.get("items", [])
    except Exception:
        return []


def search_steam_appid(folder_name: str) -> tuple[int | None, str | None, str | None]:
    """
    Tries multiple search variants for a folder name.
    Returns (appid, official_name, matched_query) or (None, None, None).
    """
    variants = folder_to_search_variants(folder_name)

    best_appid  = None
    best_name   = None
    best_query  = None
    best_score  = 0.0

    for query in variants:
        items = _steam_search(query)
        if not items:
            continue

        for item in items:
            steam_name = item.get("name", "")
            app_type   = item.get("type", "")

            # Skip DLC, movies, soundtracks — only actual games
            if app_type not in ("", "game", "app"):
                continue

            # Exact match -> return immediately
            if steam_name.lower() == folder_name.lower():
                return item["id"], steam_name, query
            if steam_name.lower() == query.lower():
                return item["id"], steam_name, query

            # Score based on token overlap with original folder name
            score = similarity_score(folder_name, steam_name)
            if score > best_score:
                best_score = score
                best_appid = item["id"]
                best_name  = steam_name
                best_query = query

        time.sleep(0.25)  # be gentle with Steam's servers

    # Accept the best hit if it has at least 50% token overlap
    if best_score >= 0.5:
        return best_appid, best_name, best_query

    return None, None, None


# ── ACF file writing ─────────────────────────────────────────────────────

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


def acf_already_exists(steamapps_dir: Path, folder_name: str) -> bool:
    """Check if any existing ACF already covers this installdir."""
    for acf in steamapps_dir.glob("appmanifest_*.acf"):
        try:
            if f'"{folder_name}"' in acf.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            pass
    return False


# ── Filesystem scan ──────────────────────────────────────────────────────

SKIP_DIRS = {
    "/proc", "/sys", "/dev", "/run", "/snap",
    "/boot", "/lost+found",
}

SKIP_NAMES = {
    "proc", "sys", "dev", "bin", "sbin", "lib", "lib64",
    "usr", "etc", "var", "tmp", "snap",
}


def find_steamapps_common_dirs(roots: list[str]) -> list[Path]:
    found = []
    for root in roots:
        print(f"\n{B}Scanning: {root}{RS}")
        for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
            p = Path(dirpath)

            if any(str(p).startswith(s) for s in SKIP_DIRS):
                dirnames.clear()
                continue

            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in SKIP_NAMES
            ]

            if p.name == "common" and p.parent.name == "steamapps":
                print(f"  {G}Found: {p}{RS}")
                found.append(p)
                dirnames.clear()

    return found


def get_scan_roots() -> list[str]:
    roots = ["/home", "/mnt", "/media", "/run/media"]
    for entry in Path("/").iterdir():
        s = str(entry)
        if s not in SKIP_DIRS and s not in roots and entry.is_dir():
            if not entry.is_symlink() and entry.name not in SKIP_NAMES:
                roots.append(s)
    return roots


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print(f"\n{W}{'='*60}")
    print("  Steam ACF Generator")
    print(f"{'='*60}{RS}\n")

    # ── Manual mode ───────────────────────────────────────────────────────
    # Usage: python3 steam_acf_generator.py --manual <steamapps_dir> <appid> <folder_name>
    if "--manual" in sys.argv:
        try:
            idx   = sys.argv.index("--manual")
            sdir  = Path(sys.argv[idx + 1])
            appid = int(sys.argv[idx + 2])
            fname = sys.argv[idx + 3]

            url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
            name = data.get(str(appid), {}).get("data", {}).get("name", fname)

            acf_path = write_acf(sdir, appid, name, fname)
            print(f"{G}Written: {acf_path}{RS}")
            print(f"  App ID: {appid}  |  Name: {name}  |  Folder: {fname}")
        except (IndexError, ValueError) as e:
            print(f"{R}Usage: --manual <steamapps_dir> <appid> <folder_name>{RS}")
            print(f"  Error: {e}")
        return

    # ── Auto scan mode ────────────────────────────────────────────────────
    roots = get_scan_roots()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        roots = sys.argv[1:]
        print(f"{Y}Using provided paths: {roots}{RS}")
    else:
        print(f"{C}Scan roots: {', '.join(roots)}{RS}")

    common_dirs = find_steamapps_common_dirs(roots)

    if not common_dirs:
        print(f"\n{R}No steamapps/common folders found.{RS}")
        print("Tip: Pass a path directly as an argument:")
        print("  python3 steam_acf_generator.py /4BTRFS")
        sys.exit(1)

    print(f"\n{G}Found {len(common_dirs)} steamapps/common folder(s).{RS}\n")

    total_written  = 0
    total_skipped  = 0
    total_notfound = 0
    not_found_list = []

    for common_dir in common_dirs:
        steamapps_dir = common_dir.parent
        print(f"\n{W}{'─'*60}")
        print(f"  Library: {steamapps_dir}")
        print(f"{'─'*60}{RS}")

        game_folders = sorted([
            d for d in common_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

        if not game_folders:
            print(f"  {Y}No game folders found.{RS}")
            continue

        print(f"  {len(game_folders)} game folders.\n")

        for game_dir in game_folders:
            folder_name = game_dir.name
            print(f"  {C}{folder_name}{RS}", end=" ", flush=True)

            if acf_already_exists(steamapps_dir, folder_name):
                print(f"-> {Y}ACF exists, skipping.{RS}")
                total_skipped += 1
                continue

            appid, official_name, matched_query = search_steam_appid(folder_name)
            time.sleep(0.3)

            if appid is None:
                print(f"-> {R}Not found on Steam.{RS}")
                total_notfound += 1
                not_found_list.append((steamapps_dir, folder_name))
                continue

            query_hint = ""
            if matched_query and matched_query != folder_name:
                query_hint = f"  {Y}(via: '{matched_query}'){RS}"

            acf_path = write_acf(steamapps_dir, appid, official_name, folder_name)
            print(f"-> {G}ID {appid} -> {acf_path.name}{RS}{query_hint}")
            print(f"     Name: {official_name}")
            total_written += 1

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{W}{'='*60}")
    print("  Done!")
    print(f"{'='*60}{RS}")
    print(f"  {G}Written:          {total_written}{RS}")
    print(f"  {Y}Already present:  {total_skipped}{RS}")
    print(f"  {R}Not found:        {total_notfound}{RS}\n")

    if not_found_list:
        helper_path = Path("/tmp/steam_manual_lookup.txt")
        lines = [
            "# Steam ACF Generator - Manual lookup list",
            "# Find the App ID for each game at https://steamdb.info",
            "# Then run:",
            "#   python3 steam_acf_generator.py --manual <steamapps_dir> <appid> <folder_name>",
            "",
        ]
        print(f"{Y}Could not match the following folders on Steam.")
        print(f"Look them up at https://steamdb.info{RS}\n")
        for sdir, fname in not_found_list:
            print(f"  {R}x{RS}  {fname}  [{sdir}]")
            lines.append(f"{sdir}\t{fname}")

        helper_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n  {C}List saved to: {helper_path}{RS}")
        print(f"\n  {W}To fix one manually:{RS}")
        print(f"  python3 steam_acf_generator.py --manual /path/to/steamapps 12345 FolderName")


if __name__ == "__main__":
    main()
