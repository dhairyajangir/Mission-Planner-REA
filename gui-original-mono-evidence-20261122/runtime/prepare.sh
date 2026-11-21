#!/usr/bin/env bash
set -euo pipefail
umask 077
work=/tmp/mission-planner-original-gui-nov21
mkdir -p "$work"/{current-debs/partial,lists/partial,root,app,results}
pkg=(bash coreutils findutils grep sed procps util-linux bubblewrap mono-devel libgdiplus libgl1 libglu1-mesa mesa-utils xvfb x11-utils x11-apps xdotool xfonts-base fontconfig fonts-dejavu-core)
# Read the distribution's signed package lists. Private status/cache keep the distro untouched.
touch "$work/dpkg-status"
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble main universe' 'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble-updates main universe' >"$work/sources.list"
apt_options=(-o Debug::NoLocking=1 -o "Dir::Etc::parts=-" -o "Dir::Etc::sourceparts=-" -o "Dir::Etc::sourcelist=$work/sources.list" -o "Dir::State::lists=$work/lists" -o "Dir::State::status=$work/dpkg-status" -o "Dir::Cache::archives=$work/current-debs" -o "Dir::Cache::pkgcache=$work/pkgcache.bin" -o "Dir::Cache::srcpkgcache=$work/srcpkgcache.bin" -o "Dir::State::extended_states=$work/extended_states" -o APT::Update::Post-Invoke::= -o APT::Update::Post-Invoke-Success::= -o Acquire::Languages=none)
apt-get "${apt_options[@]}" update >"$work/index.log" 2>&1
apt-get "${apt_options[@]}" --download-only -y --no-install-recommends install "${pkg[@]}" >"$work/download.log" 2>&1
echo "Downloaded $(find "$work/current-debs" -name '*.deb' | wc -l) verified packages"
root="$work/root"
mkdir -p "$root"/usr/{lib,bin,sbin,lib64}
for dir in lib bin sbin lib64; do
    [[ -e "$root/$dir" ]] || ln -s "usr/$dir" "$root/$dir"
done
for archive in "$work"/current-debs/*.deb; do
    dpkg-deb -x "$archive" "$root"
done
mkdir -p "$root"/{proc,dev,tmp,home/test,opt/mp,evidence}
if [[ ! -e "$root/usr/bin/mono" ]]; then ln -s mono-sgen "$root/usr/bin/mono"; fi
unzip -q -o '/mnt/e/DroneProject/The Drone Project/mission-planner-portable.zip' -d "$work/app"
find "$work/app" -name MissionPlanner.exe -print -exec sha256sum {} \;
ls -l "$root/usr/bin/"{bwrap,Xvfb,xwd,mono}
