# steam-.acf-generator-
<img width="872" height="798" alt="steam13" src="https://github.com/user-attachments/assets/e8e76aaf-d61e-4e60-8ff3-0ff7f70f1317" />
<img width="717" height="658" alt="steam54" src="https://github.com/user-attachments/assets/167d92ef-c072-4d63-9e20-c3b6ecaac6ac" />

# Steam ACF Generator
 
Automatically regenerates missing Steam `appmanifest_XXXX.acf` files by scanning your filesystem for installed game folders and looking up their App IDs via the Steam Store API.
 
No browser automation, no dependencies — pure Python 3.
 
---
 
## Why does this exist?
 
Steam tracks installed games through `.acf` files inside `steamapps/`. If these files get deleted, corrupted, or lost (e.g. after moving a library to a new drive), Steam no longer recognizes the games as installed — even though all the game data is still there. Normally you'd have to re-download everything. This tool fixes that.
 
---
 
## How it works
 
1. **Scans** your entire filesystem (or a path you specify) for `steamapps/common/` folders
2. **Reads** every subfolder inside `common/` — each one is an installed game
3. **Queries** the Steam Store API with the folder name to find the correct App ID
4. **Writes** a proper `appmanifest_XXXX.acf` file into the `steamapps/` directory
5. **Skips** games that already have a valid ACF file
---
 
## Requirements
 
- Python 3.10 or newer
- Internet connection (for the Steam Store API)
- No third-party packages needed
---
 
## Usage
 
### Automatic scan (recommended)
 
```bash
python3 steam_acf_generator.py
```
 
Scans common mount points: `/home`, `/mnt`, `/media`, `/run/media`, and root-level drives.
 
### Specify a path directly (faster)
 
```bash
python3 steam_acf_generator.py /4BTRFS
python3 steam_acf_generator.py /mnt/games /home/user
```
 
### Fix a single game manually
 
Use this for games the script couldn't find automatically:
 
```bash
python3 steam_acf_generator.py --manual /path/to/steamapps 12345 FolderName
```
 
- `/path/to/steamapps` — the steamapps folder (not the `common` subfolder)
- `12345` — the Steam App ID (find it on [steamdb.info](https://steamdb.info))
- `FolderName` — the exact name of the game's folder inside `common/`
**Example:**
 
```bash
python3 steam_acf_generator.py --manual /4BTRFS/SteamLibrary/steamapps 570 Dota2
```
 
---
 
## Match rate
 
In testing across ~160 installed games, the script matched approximately **85–90%** automatically. The remaining ~10–15% fall into categories that are difficult or impossible to resolve automatically:
 
| Category | Examples | Fixable? |
|---|---|---|
| Delisted games | `PlanetSide Arena`, `Robocraft 2`, `Warface Clutch`, `Zula EU` | ❌ Not on Steam store anymore |
| Test / beta branches | `PUBG_Test`, `PUBG_Experimental`, `paladins pts` | ❌ Not separate store entries |
| Heavy abbreviations | `CM3`, `FPH SpedV`, `CoJ Gunslinger` | ⚠️ Use `--manual` |
| Regional variants | `Zula EU` | ❌ Not a separate store entry |
| CamelCase + suffix combos | `BorderlandsGOTYEnhanced`, `BorderlandsPreSequel` | ⚠️ Use `--manual` |
 
For everything the script can't resolve, a list is saved to `/tmp/steam_manual_lookup.txt` with instructions.
