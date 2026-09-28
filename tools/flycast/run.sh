#!/bin/sh
# run.sh <US|JP> <timeline> [extra flycast args]  - Dreamcast reference run with tools/flycast/timeline.lua
# Flycast: tools/local/flycast-src (clone of ~/flycast + a Lua screenshot binding, built with Lua 5.4),
# isolated config/data under out/tmp/flycast (BIOS linked from ~/Downloads/dc_bios), real-time (Flycast's frame
# limiter is fixed on).  GB2_FC_INST=<name> gives parallel runs their own config/data directories.
R=$(dirname "$(readlink -f "$0")")/../..
reg=$1; tl=$(readlink -f "$2"); shift 2
F=$R/out/tmp/flycast; I=$F/inst/${GB2_FC_INST:-0}
# fresh state every run (VMU saves / flash / settings from earlier runs change the boot and menu timing)
rm -rf "${I:?}/cfg" "${I:?}/data"
mkdir -p $I/cfg/flycast $I/data/flycast
ln -sf ~/Downloads/dc_bios/dc_boot.bin $I/data/flycast/dc_boot.bin
ln -sf ~/Downloads/dc_bios/dc_flash.bin $I/data/flycast/dc_flash.bin
cp $R/tools/flycast/timeline.lua $I/cfg/flycast/flycast.lua
case $reg in
  US) disc="$F/disc_us/Gunbird 2 v1.000 (2000)(Capcom)(US)[!].gdi";;
  JP) disc="$F/disc_jp/Gunbird 2 v1.002 (2000)(Capcom)(JP)(en)[!].gdi";;
esac
GB2_TIMELINE=$tl XDG_CONFIG_HOME=$I/cfg XDG_DATA_HOME=$I/data timeout 1800 \
  $R/tools/local/flycast-src/build/flycast -config audio:backend=null "$@" "$disc"
