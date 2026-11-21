grep -Fq 'appload time' /evidence/release.log
echo 'Pressed Ctrl+P from the disconnected main window.'
xdotool key ctrl+p
for ((i=0;i<60;i++)); do
    if xdotool search --onlyvisible --maxdepth 1 --name '^PluginManager$' >/dev/null; then break; fi
    sleep 1
done
sleep 5
snapshot manager-open
sleep 12
snapshot manager-settled
cp "$XDG_DATA_HOME/Mission Planner/config.xml" /evidence/final-user-config.xml
echo 'Observation finished with no input to the PluginManager window.'
