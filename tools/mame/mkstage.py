#!/usr/bin/env python3
"""Timeline: maintenance code -> Stage Select -> start <stage> with 1P character <char> (0-based Jiki index).
Prints lines and the frame at which the stage starts (as a comment 'START <frame>').
usage: mkstage.py <stage 1-8> <char> [round] [--p2 <Jiki index>] [--mode <n>]
  --mode: PlayMode rights from '1 Stage Play' (1 Full Play, 2 Stage Demo, 3 Inplay Demo, 4 Ending Demo)"""
import sys, subprocess, os, argparse
ap = argparse.ArgumentParser()
ap.add_argument('stage', type=int); ap.add_argument('char', type=int); ap.add_argument('round', type=int, nargs='?', default=1)
ap.add_argument('--p2', type=int, default=None); ap.add_argument('--mode', type=int, default=0)
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
lines = subprocess.run([sys.executable, here + '/mkcode.py', '400', '52048', '/tmp'], capture_output=True, text=True).stdout.splitlines()
lines = [l for l in lines if 'snap' not in l]
t = 1300
def tap(n):
    global t
    lines.append(f"{t} tap 3 {n}"); t += 10
for _ in range(9): tap('P1 Up')
tap('P1 Button 1'); t += 50
for _ in range(a.char): tap('P1 Right')        # 1P Character
tap('P1 Down')                                 # -> 2P Character (0 = NoUse)
if a.p2 is not None:
    # values 0 = NoUse, 1.. = Jiki0..; the menu skips 1P's value, so one Right less once past it
    for _ in range(a.p2 + 1 - (a.p2 > a.char)): tap('P1 Right')
tap('P1 Down')                                 # -> Round
for _ in range(a.round - 1): tap('P1 Right')
tap('P1 Down')                                 # -> Stage
for _ in range(a.stage - 1): tap('P1 Right')
if a.mode:
    tap('P1 Down')                             # -> PlayMode
    for _ in range(a.mode): tap('P1 Right')
t += 10
lines.append(f"{t} tap 5 1 Player Start")
print('\n'.join(lines))
print(f"# START {t}")
