#!/bin/bash
# Start or stop the disposable ArduCopter SITL used by PageActionProbe (Ubuntu-E). Simulator only.
# usage: page-action-sitl.sh start | stop
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
case $1 in
  start)
    pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
    mkdir -p ~/page-action-sitl; cd ~/page-action-sitl
    nohup ~/ap-snapshot/build/sitl/bin/arducopter -w -M + -I 0 -s 1 --home -35.363261,149.165230,584,0 > sitl.log 2>&1 &
    sleep 3; pgrep -f 'build/sitl/bin/arducopter' | head -1 | sed 's/^/sitl pid /'
    ;;
  run)
    # foreground: meant to be the long-lived process of a hidden wsl.exe started by the caller (a detached start did not survive a client connection)
    pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
    # same shape as the sitl-exit-check run that worked: fresh working directory, simulator as a child (no exec) of this shell
    rm -rf ~/page-action-sitl; mkdir -p ~/page-action-sitl; cd ~/page-action-sitl
    ~/ap-snapshot/build/sitl/bin/arducopter -w -M + -I 0 -s 1 --home -35.363261,149.165230,584,0 > sitl.log 2>&1
    echo "simulator exited with status $? at $(date +%T)" > exit.txt
    ;;
  wait)
    # wait up to 90 s for the simulator to report it is waiting for a client; print what is alive either way
    for i in $(seq 1 90); do
      if grep -q 'Waiting for connection' ~/page-action-sitl/sitl.log 2>/dev/null; then echo "simulator ready after ${i}s"; exit 0; fi
      sleep 1
    done
    echo "simulator NOT ready; alive: $(pgrep -x arducopter)"; ls -la ~/page-action-sitl 2>&1 | head -4; tail -n 3 ~/page-action-sitl/sitl.log 2>&1
    exit 1
    ;;
  stop)
    pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
    mkdir -p "$REPO/sitl-evidence/page-actions"
    cp ~/page-action-sitl/sitl.log "$REPO/sitl-evidence/page-actions/sitl.log"
    echo stopped
    ;;
esac
