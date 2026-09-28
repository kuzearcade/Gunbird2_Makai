#!/bin/sh
# wrapper: portable JDK + Ghidra headless
R=$(dirname "$(readlink -f "$0")")/..
export JAVA_HOME=$(ls -d $R/tools/local/jdk-21*)
export PATH=$JAVA_HOME/bin:$PATH
export GB2ROOT=$R
exec $R/tools/local/ghidra_12.1.4_PUBLIC/support/analyzeHeadless "$@"
