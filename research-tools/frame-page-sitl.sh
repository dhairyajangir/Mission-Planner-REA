#!/bin/bash
# Start, wait for, or stop a disposable ArduCopter SITL of a chosen frame for PageFrameProbe (Ubuntu-E). Simulator only.
# usage: frame-page-sitl.sh run  <model> <binary: arducopter|arducopter-heli> <workdir name> [nowipe]   (foreground; give it a hidden wsl.exe)
#        frame-page-sitl.sh wait <workdir name>
#        frame-page-sitl.sh stop <workdir name> <log destination dir> <log file name>
case $1 in
  run)
    pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
    W=~/$4
    if [ "$5" != nowipe ]; then rm -rf "$W"; WIPE=-w; else WIPE=; fi
    mkdir -p "$W"; cd "$W"
    ~/ap-snapshot/build/sitl/bin/$3 $WIPE --model "$2" -I 0 -s 1 --home -35.363261,149.165230,584,0 > sitl.log 2>&1
    echo "simulator exited with status $? at $(date +%T)" > exit.txt
    ;;
  wait)
    for i in $(seq 1 90); do
      if grep -q 'Waiting for connection' ~/$2/sitl.log 2>/dev/null; then echo "simulator ready after ${i}s"; exit 0; fi
      sleep 1
    done
    echo "simulator NOT ready"; tail -n 3 ~/$2/sitl.log 2>&1; exit 1
    ;;
  stop)
    pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
    mkdir -p "$3"; cp ~/$2/sitl.log "$3/$4"
    echo stopped
    ;;
esac
