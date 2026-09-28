#!/bin/sh
# run.sh <romdir> <timeline> [extra mame args]   - headless, unthrottled
R=$(dirname "$(readlink -f "$0")")/../..
romdir=$1; tl=$(readlink -f $2); shift 2
NV=${GB2_NVRAM:-$R/out/tmp/nvram}
mkdir -p $NV $R/out/tmp/cfg $R/out/snap
cd $HOME/mame && GB2_TIMELINE=$tl timeout 1800 ./mame gunbird2 -rompath $romdir -video none -sound none -nothrottle \
  -skip_gameinfo -nvram_directory $NV -cfg_directory $R/out/tmp/cfg -snapshot_directory $R/out/snap \
  -autoboot_script $R/tools/mame/timeline.lua "$@"
