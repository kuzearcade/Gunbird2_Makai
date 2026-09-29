# Gunbird 2 – Morrigan backport (Dreamcast → arcade)

Morrigan Aensland was added to the Dreamcast release of Psikyo's *Gunbird 2* as a Capcom guest character. The
original arcade game (Psikyo PS5 board, MAME set `gunbird2`) never had her. This project backports her from the
Dreamcast release to the arcade game: her sprites, shots, bombs, sounds, story scenes, endings and ranking animation.
It targets the real PS5 board's limits, so the result could run on real hardware as well as in MAME.

No game data is included. Everything is extracted from your own copies of the arcade ROMs and the Dreamcast disc,
then converted and patched in by the tools here.

## Goals

- **Faithful to the Dreamcast.** US v1.000 is the reference; JP v1.002 was checked for gameplay differences and has
  none. Her speed, hitboxes, per-hit damage, bomb and charged shots match Dreamcast reference traces
  taken with Flycast.
- **Real hardware limits.** Everything fits the PS5 board as it can be populated:
  - program ROM 1 MB;
  - data ROM 512 KB;
  - sound ROM 4 MB (the YMF278B limit);
  - graphics ROM bank 3 filled with 64M EPROMs, the sockets' capacity.
  See `MORRIGAN_BACKPORT_PLAN.md` §0.1.
- **The original game is left untouched.** With Morrigan locked, the patched set plays exactly like the original.
  This is checked by whole-game regression runs for every character and every two-player pairing.
- **English and Japanese.** Her story text is present for both regions (region jumper / MAME "Region" setting).
- **Arcade-style unlock.** Morrigan is unlocked with a maintenance code, like the arcade's own Aine secret.

## Features

- **Playable Morrigan** as 1P or 2P: all shot power levels, sub-shot, charged shots (all gauge levels, including the
  full-screen level-3 attack), bomb, death, respawn and continue.
- **Character select:** after unlocking, move to `?` and press **Up** to pick her. Her portraits, slot icon and select
  voice follow the Dreamcast's random-pick rules.
- **Sound:** her voices and effects from the Dreamcast sound banks (20 sound IDs, 17 samples), resampled for the arcade's YMF278B. Levels and
  pitch are fitted to the Dreamcast, and her item-pickup voices are included. To make room, 27 samples that the
  original game never plays were removed; they are kept locally in `unused_arcade_samples_removed/`.
- **Story:** all 36 of her stage-demo scenes (every stage, alone or with each partner), with portraits and English
  and Japanese text.
- **Endings:** her solo ending and every pair ending, converted to 8-bit colour tiles.
- **HUD and menus:** HUD life icons, all-clear bonus tally, name entry, and her animated high-score ranking icon.
  In the maintenance Stage Select she appears as "Jiki6", the Dreamcast's internal name.
- **ROM test:** the boot-time ROM checksums are recomputed on every build, so the game's own ROM test passes.
- **Not included:** the Dreamcast-only voiced dialogue and ending voices (no sound ROM space) and the Sofdec staff-roll
  movie (the board has no video decoder). On the Dreamcast, the staff roll is also skipped in its "Arcade" screen mode.

## Using the result

- **ROM set:** `gunbird2m`, a clone of `gunbird2`. It's the same PS5 board, but graphics bank 3 uses 64M EPROMs:
  - `3l_m.u6` and `3h_m.u13`, 8 MB each, instead of 4 MB.
  - A MAME driver entry for it is in `tools/mame/gunbird2m_driver.patch`.
- **Unlocking Morrigan:**
  1. Enter Test Mode (Service switch, F2 in MAME).
  2. Choose **Maintenance Code** (fifth item).
  3. Enter **5-1-9-9-4**. The code is saved to the EEPROM.
- **Picking her:** on character select, move to `?` and press **Up**.
- **Other codes:** the arcade's own maintenance codes still work, e.g. 5-1-0-2-4 for Aine.

## Requirements

Inputs (not included; place them as shown, all git-ignored):

| File | Where |
|---|---|
| MAME `gunbird2` ROM set (`gunbird2.zip`) | `mame_roms/` |
| Dreamcast *Gunbird 2* US v1.000 disc (GDI) | extracted to `assets/dc/US/fs/` (see below) |
| Dreamcast JP v1.002 disc (GDI) – optional, for the JP comparison | `assets/dc/JP/fs/` |

Tools:

- Linux, **Python 3** with `numpy` and `Pillow`.
- **SH cross toolchain**: Ubuntu's `binutils-sh4-linux-gnu` and `gcc-15-sh4-linux-gnu` (plus `cpp-15-…`,
  `gcc-15-…-base`).
  - They don't need root: download them with `apt-get download` and unpack each with `dpkg -x <deb> tools/local/root`.
  - The wrappers in `tools/bin/` expect that location.
  - `sh2-cc` compiles with the SH-4 `cc1` in no-FPU mode, then assembles with `--isa=sh2`, which rejects any
    instruction the arcade's SH-2 lacks.
- **MAME** built from source, with `tools/mame/gunbird2m_driver.patch` applied (made against MAME 0.289). The test tools
  expect it at `~/mame`.
- Optional, only for research and reference checks:
  - Ghidra 12 with a JDK 21 (`tools/ghidra_headless.sh`, `re/ghidra_scripts/`);
  - Flycast with the Lua screenshot binding (`tools/flycast/`), plus a Dreamcast BIOS in `~/Downloads/dc_bios`;
  - `ffmpeg`.

## Build

```sh
# 1. arcade analysis images -> assets/arcade/ (prog_be.bin, pdata_be.bin, gfx.bin, sound.bin)
python3 tools/arcade_images.py mame_roms/gunbird2.zip
# RAM image after boot (code copied to RAM) -> assets/arcade/ram_init.bin
(cd ~/mame && GB2_FRAMES=600 GB2_OUT=$OLDPWD/assets/arcade/ram_init.bin ./mame gunbird2 \
   -rompath $OLDPWD/mame_roms -video none -sound none -nothrottle -skip_gameinfo \
   -autoboot_script $OLDPWD/tools/mame/dumpram.lua)

# 2. Dreamcast files: extract the GDI's data track (track03.bin) and keep a copy of the main program
python3 tools/gdi_extract.py "<disc>/track03.bin" assets/dc/US/fs
cp assets/dc/US/fs/1ST_READ.BIN re/1st_read_US.bin          # same for JP -> assets/dc/JP/fs, re/1st_read_JP.bin

# 3. extract the Dreamcast story data (scene lists, ending scripts, Japanese text as arcade font codes)
python3 tools/stagedemo_extract.py # -> out/stagedemo/scenes.json (+ img/)
python3 tools/endextract.py        # -> out/stagedemo/endings.json
python3 tools/jptranscribe.py      # -> out/stagedemo/jp_codes.json
python3 tools/jpend.py             # -> out/stagedemo/end_jp_codes.json

# 4. generate Morrigan's data (order matters)
python3 tools/port_sound.py        # sound ROM + her sound IDs      -> out/snd/, src/gen_sound.*
python3 tools/make_gfx.py          # sprite / select / portrait / ranking tiles + palettes -> out/gfx/, src/gen_gfx.*
python3 tools/port_morrigan.py     # her scripts, sprite frames, hit data  -> out/res/morrigan.json
python3 tools/port_stagedemo.py    # story scenes                  -> src/gen_story.*
python3 tools/port_endings.py      # endings (after make_gfx: appends to out/gfx/place.json) -> src/gen_endings.*
python3 tools/port_ranking.py      # ranking animation             -> src/gen_ranking.c

# 5. compile the C/asm patches, apply hooks and patches, write the ROM set
python3 tools/build.py --set gunbird2m                        # -> out/roms/gunbird2m/ (+ gunbird2m.crc.json)

# play
~/mame/mame gunbird2m -rompath out/roms
```

Converted game data is never committed: `src/gen_*`, `out/gfx`, `out/res`, `out/end`, `out/snd`, `out/obj` and the
generated `out/stagedemo` JSON are git-ignored and recreated by steps 3-4 (after that, code-only changes need step 5
only).  A fresh clone plus the ignored inputs builds bit-identical ROMs.  Kept in git are hand-made inputs: layout
and patch lists in `src/`, the transcribed story text (`src/story/*.json`), research maps in `re/` and three address
maps in `out/stagedemo/` (`end_text_owner`, `end_text_pairs`, `engine_match`). `build.py --set gunbird2` (the stock 56 MB layout) stops
with a graphics overflow, because the ending tiles need bank 3's second half.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | Arcade-side code: C replacements and additions, asm hooks (`hooks.txt`), raw/pointer patches (`patches.txt`), generated tables (`gen_*`), layout config (`morrigan_layout.json`) |
| `tools/` | Extractors, converters and porters, disassemblers (`seqdis.py`, SH-2 via `tools/bin/sh-objdump`), `build.py` |
| `tools/mame/` | MAME timeline harness (`timeline.lua`, `run.sh`), Stage Select / code helpers, regression tests, driver patch |
| `tools/flycast/` | Dreamcast reference harness (Flycast + Lua) |
| `re/` | Reverse-engineering notes (`NOTES.md`), symbol maps, DC↔arcade object and function maps, sequence-VM opcode data, Ghidra scripts |
| `MORRIGAN_BACKPORT_PLAN.md` | Original plan and hardware-capacity study |
| `PORT_TODO.md` | Detailed task list with status |

## Testing

All test tools compare the patched set with the original in MAME, or with the Dreamcast in Flycast.  First create
their inputs (git-ignored, in `out/tmp/`) with `python3 tools/mame/regress_setup.py` after building gunbird2m: the
regression EEPROM, the Morrigan-unlocked EEPROM, both built from the ROM set's default EEPROM, and the verified
select-screen inputs (about 2 minutes).

| Command | What it checks |
|---|---|
| `tools/mame/regress_game.py out/tmp/eeprom_regress.bin --one --two` | Whole games from coin to attract mode, for all 6 original characters and all 30 two-player pairings. Screen hashes every 4 frames must match. Select inputs come from `tools/mame/select_paths.py`. |
| `tools/mame/regress_select.py <eeprom>` | Select screen and the first seconds of play, pixel for pixel |
| `tools/mame/regress_sound.py <eeprom> --set gunbird2m` | Sound-chip register writes for all 6 characters, including bombs, charges and continues |
| `tools/mame/check_stagedemo.py regress\|morrigan <eeprom>` | Original stage demos unchanged; contact sheets of all Morrigan scenes |
| `tools/trace_compare.py` | Morrigan vs the Dreamcast: speed, hitboxes, per-hit damage, time to kill |

The regression EEPROM has Aine unlocked and Morrigan locked; `tools/mame/regress_setup.py` and `re/NOTES.md`
("Whole-game regression") describe its layout. With Morrigan unlocked, the `?` slot on the select screen draws from a larger random range, so the game
legitimately takes a different course from the original.

## To do

- **Real-PCB test (open).**
  - Palette lines `0x100+`: her in-game palette uses palette RAM that the original game never writes. It works in
    MAME but hasn't been verified on a PS5 board.
  - The 64M bank-3 EPROM pair also needs a check on real hardware.
- **Not planned (Dreamcast-only):** stage-demo and ending voices (no sound ROM space), and the staff-roll movie (no
  video playback on the board).

See `PORT_TODO.md` for the full, itemised status and `re/NOTES.md` for the technical findings behind each part.

## Legal

This repository contains only tools, patches and notes. *Gunbird 2* is © Psikyo and Morrigan is © Capcom; you need
your own legally obtained ROMs and disc to build anything.
