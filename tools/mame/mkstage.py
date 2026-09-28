#!/usr/bin/env python3
"""Timeline: maintenance code -> Stage Select -> start <stage> with 1P character <char> (0-based Jiki index).
Prints lines and the frame at which the stage starts (as a comment 'START <frame>').
usage: mkstage.py <stage 1-8> <char> [round]"""
import sys, subprocess, os
stage = int(sys.argv[1]); char = int(sys.argv[2]); rnd = int(sys.argv[3]) if len(sys.argv) > 3 else 1
here = os.path.dirname(os.path.abspath(__file__))
lines = subprocess.run([sys.executable, here + '/mkcode.py', '400', '52048', '/tmp'], capture_output=True, text=True).stdout.splitlines()
lines = [l for l in lines if 'snap' not in l]
t = 1300
def tap(n):
    global t
    lines.append(f"{t} tap 3 {n}"); t += 10
for _ in range(9): tap('P1 Up')
tap('P1 Button 1'); t += 50
for _ in range(char): tap('P1 Right')          # 1P Character
tap('P1 Down'); tap('P1 Down')                 # -> Round
for _ in range(rnd - 1): tap('P1 Right')
tap('P1 Down')                                 # -> Stage
for _ in range(stage - 1): tap('P1 Right')
t += 10
lines.append(f"{t} tap 5 1 Player Start")
print('\n'.join(lines))
print(f"# START {t}")
