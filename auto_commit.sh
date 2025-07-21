#!/bin/bash

cd "$(dirname "$0")"

git add gym_bot.db
git commit -m "chore: 自动备份健身数据 $(date '+%Y-%m-%d %H:%M:%S')" || exit 0
git push 