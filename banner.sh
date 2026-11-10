#!/bin/bash

echo -ne "\\033[2J\033[3;1f"
for candidate in \
	"$(dirname "$0")/assets/banner.txt" \
	"$HOME/Heroku/assets/banner.txt" \
	"$HOME/Kanjo/assets/banner.txt"
do
	if [ -f "$candidate" ]; then
		cat "$candidate"
		break
	fi
done
printf "\n\n\033[1;32mKanjo is running!\033[0m\n"
