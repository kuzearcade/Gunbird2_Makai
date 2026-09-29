#!/usr/bin/env python3
"""Create the git-ignored test inputs in out/tmp/ (run after tools/build.py --set gunbird2m):
  eeprom_regress.bin   MAME's default gunbird2 EEPROM (eeprom-gunbird2.bin from mame_roms/gunbird2.zip) with Aine
                       unlocked and Morrigan locked - for regress_game.py / regress_select.py / regress_sound.py
  eeprom_morrigan.bin  the same default with Morrigan unlocked (maintenance code 5-1-9-9-4) - for trace_compare.py,
                       check_stagedemo.py and Morrigan test runs
  select_paths.json    verified select-screen inputs for every character / 2P pair (tools/mame/select_paths.py,
                       ~2 minutes; needs the gunbird2m build in out/roms)
EEPROM secret block (16-bit big-endian words, src/maint.c): 0x18 play time (u32), 0x1C credits played, 0x1E Aine flag
(0 none, 1 random may pick her, 2 Down on '?'), 0x20 Morrigan ('Mo' = unlocked, the patched game only),
0x2E checksum = (s16)time + plays + Aine flag.
usage: regress_setup.py [--no-paths] [--force]"""
import os, sys, zipfile, struct, subprocess
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
TMP = ROOT + '/out/tmp'


def eeprom(plays=0, aine=0, morrigan=False):
    b = bytearray(zipfile.ZipFile(ROOT + '/mame_roms/gunbird2.zip').read('eeprom-gunbird2.bin'))
    time = struct.unpack('>I', b[0x18:0x1C])[0]
    b[0x1C:0x20] = struct.pack('>HH', plays, aine)
    b[0x20:0x22] = b'Mo' if morrigan else b'\0\0'
    b[0x2E:0x30] = struct.pack('>H', (time + plays + aine) & 0xFFFF)
    return bytes(b)


def main():
    os.makedirs(TMP, exist_ok=True)
    force = '--force' in sys.argv
    for name, data in (('eeprom_regress.bin', eeprom(plays=30, aine=2)),
                       ('eeprom_morrigan.bin', eeprom(morrigan=True))):
        p = f'{TMP}/{name}'
        if os.path.exists(p) and open(p, 'rb').read() == data: print(f'{name}: up to date'); continue
        open(p, 'wb').write(data); print(f'{name}: written')
    if '--no-paths' in sys.argv: return
    if os.path.exists(TMP + '/select_paths.json') and not force:
        print('select_paths.json: exists (--force to search again)'); return
    if not os.path.exists(ROOT + '/out/roms/gunbird2m/1_prog_h.u17'):
        sys.exit('select_paths.json: build gunbird2m first (tools/build.py --set gunbird2m)')
    print('select_paths.json: searching (tools/mame/select_paths.py) ...', flush=True)
    r = subprocess.run([sys.executable, ROOT + '/tools/mame/select_paths.py', TMP + '/eeprom_regress.bin'])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
