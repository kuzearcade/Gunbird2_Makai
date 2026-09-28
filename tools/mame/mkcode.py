#!/usr/bin/env python3
"""Emit timeline lines that open Test Mode -> Maintenance Code and enter a 5-digit code.
usage: mkcode.py <start_frame> <code e.g. 51994> <snapdir> [--exit]"""
import sys
f = int(sys.argv[1]); code = sys.argv[2]; snap = sys.argv[3]
out = [f"{f} press Service Mode", f"{f+20} release Service Mode"]
t = f + 200
def tap(name):
    global t
    out.append(f"{t} tap 3 {name}"); t += 10
for _ in range(4): tap("P1 Down")
tap("P1 Button 1"); t += 60
out.append(f"{t} snap {snap}/code_screen.png"); t += 5
for i, ch in enumerate(code):
    d = int(ch)
    if d <= 5:
        for _ in range(d): tap("P1 Up")
    else:
        for _ in range(10 - d): tap("P1 Down")
    if i < 4: tap("P1 Right")
out.append(f"{t} snap {snap}/code_entered.png"); t += 5
tap("P1 Button 1")
out.append(f"{t+30} snap {snap}/code_result.png")
out.append(f"{t+300} snap {snap}/code_after.png")
if '--exit' in sys.argv: out.append(f"{t+301} exit")
print('\n'.join(out))
