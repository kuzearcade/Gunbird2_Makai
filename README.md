# Gunbird 2 Makai (Morrigan Backport)

Morrigan Aensland was added to the Dreamcast release of Psikyo's *Gunbird 2* as a Capcom guest character. The
original arcade game (Psikyo PS5 board, MAME set `gunbird2`) never had her. This project (`Gunbird2_Makai`)
backports her from the Dreamcast release to the arcade game: her sprites, shots, bombs, sounds, story scenes,
endings and ranking animation. It targets the real PS5 board's limits, so the result could run on real hardware as
well as in MAME.

The name comes from **Makai** (魔界), the demon realm Morrigan comes from.

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
  - A MAME driver entry for it is in `tools/mame/gunbird2m_driver.patch`; MAME lists it as "Gunbird 2 Makai
    (Morrigan Backport)".
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
python3 tools/story_text.py        # story text read back from the DC images (glyph table re/story_glyphs.json)
                                   #    -> out/stagedemo/stagedemo_text.json, ending_text.json

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
and patch lists in `src/`, research maps in `re/`, three address maps in `out/stagedemo/` (`end_text_owner`,
`end_text_pairs`, `engine_match`) and `re/story_glyphs.json`, the glyph-hash table `story_text.py` uses to read the
story text from the Dreamcast images (no text and no pixels; `story_text.py --learn --from <dir>` rebuilds it from
transcriptions). `build.py --set gunbird2` (the stock 56 MB layout) stops
with a graphics overflow, because the ending tiles need bank 3's second half.

## Checksums

**Input: MAME `gunbird2` set** (`mame_roms/gunbird2.zip`, the parent set, "Gunbird 2 (set 1)"; `mame -verifyroms
gunbird2` reports it good). The zip's own checksum depends on how it was packed, so the table lists its files:

| File | Size | CRC32 | SHA-1 |
|---|---:|---|---|
| `1_prog_h.u17` | 524288 | `7328d8bf` | `c640de1ab5b32400b2d77e0dc6e3ee0f78ab7803` |
| `2_prog_l.u16` | 524288 | `76f934f0` | `cf197796d66f15639a6b3d5311c18da33cefd06b` |
| `3_pdata.u1` | 524288 | `a5b697e6` | `947f124fa585c2cf77c6571af7559bd652897b89` |
| `0l.u3` | 8388608 | `5c826bc8` | `74fb6b242b4c5fe5365cfcc3029ed6da4cf3a621` |
| `0h.u10` | 8388608 | `3df0cb6c` | `271d276fa0f63d84e458223316a9517865fc2255` |
| `1l.u4` | 8388608 | `1558358d` | `e3b9c3da4e9b29ffa9568b57d14fe2b600aead68` |
| `1h.u11` | 8388608 | `4ee0103b` | `29bbe0162dda39919fcd188ea4a6b7b5f20366ff` |
| `2l.u5` | 8388608 | `e1c7a7b8` | `b5f6e5d53e21928197773df7dde0e7c83f4082af` |
| `2h.u12` | 8388608 | `bc8a41df` | `90460b11eea778f17cf8be67430e2ab149680686` |
| `3l.u6` | 4194304 | `0229d37f` | `f9d98d1d2dda2d552b2a46c76b4c7fc84b1aa4c6` |
| `3h.u13` | 4194304 | `f41bbf2b` | `b705274e392541e2f513a4ae4bae543c03be0913` |
| `sound.u9` | 4194304 | `f19796ab` | `b978f0550ebd675e8ce9d9edcfcc3f6214e49e8b` |
| `eeprom-gunbird2.bin` | 256 | `7ac38846` | `c5f4b05a94211f3c96b8c472adbe634f2e77d753` |

**Input: Dreamcast discs** (Redump-verified GDI dumps). The build reads the US disc's `track03.bin`; the JP disc is
optional (Japanese-version comparison and research tools).

| Disc / file | Size | CRC32 | SHA-1 |
|---|---:|---|---|
| *Gunbird 2 v1.000 (2000)(Capcom)(US)[!]* `.gdi` | 87 | `ae10ab3d` | `3f6db4a24a9ef1f4efaf36985c5cb9cc2f56013d` |
| US `track01.bin` | 1232448 | `bdf0a8c9` | `e70773bf5b99cb33d5f2c51934ffea67a9311d8f` |
| US `track02.raw` | 1237152 | `48fff429` | `b0d28980a64765c022b4b3e47244aad32a345270` |
| US `track03.bin` | 1185760800 | `ca4876bb` | `d33dd712e9c908705e5d53dd924962446faf9dff` |
| *Gunbird 2 v1.002 (2000)(Capcom)(JP)(en)[!]* `.gdi` | 87 | `ae10ab3d` | `3f6db4a24a9ef1f4efaf36985c5cb9cc2f56013d` |
| JP `track01.bin` | 1232448 | `e697c743` | `a64257a22406656d86b4fa89b0ebd5b32ce1ba81` |
| JP `track02.raw` | 1735776 | `0de03f29` | `db680939aae4bf61d0e588414c72a47c6dd92cdd` |
| JP `track03.bin` | 1185760800 | `ba049f36` | `a6e18b33ab2fa5ea6ca74c1de3d7bf8d5752304b` |

**Output: `out/roms/gunbird2m/`** from `tools/build.py --set gunbird2m`. The program ROMs (`1_prog_h`, `2_prog_l`,
`3_pdata`) contain compiled code, so they match only when built with the same SH toolchain: Ubuntu
`gcc-15-sh4-linux-gnu` 15.2.0-16ubuntu1cross2 and `binutils-sh4-linux-gnu` 2.46-3ubuntu2. The other files don't
depend on the compiler.

| File | Size | CRC32 | SHA-1 |
|---|---:|---|---|
| `1_prog_h.u17` | 524288 | `4b426396` | `2670d4ca9252d752e2f0686bb174478fd030836c` |
| `2_prog_l.u16` | 524288 | `6df5eab9` | `bac346a49cd57e72e7171563c461e037a773e8c0` |
| `3_pdata.u1` | 524288 | `59e702c2` | `165e515410b633ea7a18dbaec22f1e78d5bb0287` |
| `0l.u3` | 8388608 | `5c826bc8` | `74fb6b242b4c5fe5365cfcc3029ed6da4cf3a621` |
| `0h.u10` | 8388608 | `3df0cb6c` | `271d276fa0f63d84e458223316a9517865fc2255` |
| `1l.u4` | 8388608 | `1558358d` | `e3b9c3da4e9b29ffa9568b57d14fe2b600aead68` |
| `1h.u11` | 8388608 | `4ee0103b` | `29bbe0162dda39919fcd188ea4a6b7b5f20366ff` |
| `2l.u5` | 8388608 | `e1c7a7b8` | `b5f6e5d53e21928197773df7dde0e7c83f4082af` |
| `2h.u12` | 8388608 | `bc8a41df` | `90460b11eea778f17cf8be67430e2ab149680686` |
| `3l_m.u6` | 8388608 | `21bec42f` | `20ef3142aa7cf48786440e96bde2a0b76986f4ed` |
| `3h_m.u13` | 8388608 | `2f7cbfd4` | `e3b758959640321f0a8ef04eac3e5bcec1e6d4cc` |
| `sound.u9` | 4194304 | `ba917b65` | `b5128356b99ef7b8da3e85b1e52631ae95ace0f5` |
| `eeprom-gunbird2.bin` | 256 | `7ac38846` | `c5f4b05a94211f3c96b8c472adbe634f2e77d753` |

Banks 0-2 and the EEPROM image are the original files, unchanged. `build.py` also writes these values to
`out/roms/gunbird2m.crc.json`; compare against it after a build.

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
