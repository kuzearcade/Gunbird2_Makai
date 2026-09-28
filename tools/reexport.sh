#!/bin/sh
# Re-apply symbol files and re-export decompilation/listings for arcade + DC US/JP.
R=$(dirname "$(readlink -f "$0")")/..
cd $R
gen_dc_syms() {  # $1 = US|JP
  python3 tools/lst_strrefs.py re/1st_read_$1.bin 8c010000 le re/export/dc_$1.lst > re/export/dc_$1_strrefs.tsv
  python3 tools/syms_from_asserts.py re/export/dc_$1_strrefs.tsv > re/dc_$1.auto.sym
}
for R1 in US JP; do
  [ -f re/export/dc_$R1.lst ] && gen_dc_syms $R1
  cat re/dc_$R1.auto.sym re/dc_$R1.sym 2>/dev/null | grep -v '^#' > re/export/dc_$R1.allsym
  tools/ghidra_headless.sh re/ghidra_proj dc_$R1 -process 1st_read_$R1.bin -noanalysis -scriptPath re/ghidra_scripts \
    -postScript ApplySymbols.java $R/re/export/dc_$R1.allsym -postScript ExportAll.java $R/re/export/dc_$R1 > re/export/dc_${R1}_exp.log 2>&1 &
done
touch re/arcade.sym
tools/ghidra_headless.sh re/ghidra_proj arcade -process prog_be.bin -noanalysis -scriptPath re/ghidra_scripts \
  -postScript ApplySymbols.java $R/re/arcade.sym -postScript ExportAll.java $R/re/export/arcade > re/export/arcade_exp.log 2>&1 &
wait
grep -P "^060" re/export/arcade.lst > re/export/arcade_ram.lst
python3 tools/lst_strrefs.py assets/arcade/ram_init.bin 06000000 be re/export/arcade_ram.lst > re/export/arcade_strrefs.tsv
grep -h "applied\|functions:" re/export/*_exp.log
