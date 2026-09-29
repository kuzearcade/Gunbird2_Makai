#!/usr/bin/env python3
"""Write the checksums of the current build (out/roms/gunbird2m.crc.json, from tools/build.py --set gunbird2m) into
the gunbird2m entry of the MAME driver and regenerate tools/mame/gunbird2m_driver.patch.  Rebuild MAME afterwards
(make in the MAME tree) and check with: mame -verifyroms gunbird2m -rompath out/roms
usage: sync_driver_crcs.py [mame source tree, default ~/mame]"""
import os, sys, re, json, subprocess
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
MAME = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/mame')
DRIVER = MAME + '/src/mame/psikyo/psikyosh.cpp'


def main():
    crc = json.load(open(ROOT + '/out/roms/gunbird2m.crc.json'))
    src = open(DRIVER).read()
    a = src.index('ROM_START( gunbird2m )'); b = src.index('ROM_END', a)
    block = src[a:b]
    changed = []
    def fix(m):
        name = m.group(2)
        if name not in crc: return m.group(0)
        c, sha, size = crc[name]
        new = f'{m.group(1)}CRC({c}) SHA1({sha}) )'
        if new != m.group(0): changed.append(name)
        return new
    # ROM_LOAD...( "name", offset, length, [BAD_DUMP] CRC(...) SHA1(...) )
    block = re.sub(r'(ROM_LOAD\w*\(\s*"([^"]+)",\s*0x[0-9a-fA-F]+,\s*0x[0-9a-fA-F]+,\s*)(?:BAD_DUMP\s+)?CRC\([0-9a-f]+\)\s*'
                   r'SHA1\([0-9a-f]+\)\s*\)', fix, block)
    missing = [n for n in re.findall(r'ROM_LOAD\w*\(\s*"([^"]+)"', block) if n not in crc]
    if missing: sys.exit(f'not in the build output: {missing}')
    src = src[:a] + block + src[b:]
    src = src.replace('Checksums are placeholders: the ROMs are rebuilt by the project.',
                      'Checksums: the project build, written by tools/mame/sync_driver_crcs.py.')
    open(DRIVER, 'w').write(src)
    patch = subprocess.run(['git', 'diff', 'src/mame/psikyo/psikyosh.cpp', 'src/mame/mame.lst'], cwd=MAME,
                           capture_output=True, text=True, check=True).stdout
    open(ROOT + '/tools/mame/gunbird2m_driver.patch', 'w').write(patch)
    print(f'{DRIVER}: updated {changed or "nothing (already current)"}; tools/mame/gunbird2m_driver.patch regenerated')


if __name__ == '__main__':
    main()
