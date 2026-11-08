#!/bin/bash
# Reproduce the waf call the NetworkingWebServerPPP autotest makes, to see why it exits 1.
source ~/venv-ap/bin/activate
cd ~/ap-snapshot || exit 1
./modules/waf/waf-light build --target bin/ardurover 2>&1 | tail -15 | cut -c1-220
echo "exit=${PIPESTATUS[0]}"
