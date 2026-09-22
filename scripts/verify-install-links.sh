#!/usr/bin/env bash

set -euo pipefail

master=${1:-"$HOME/agent-skills"}
skills=(
  research-experiment-design
  research-literature-review
  research-paper-audit
  research-reproducibility
  research-result-verification
)

if [[ ! -d "$master" ]]; then
  printf 'ERROR: master directory not found: %s\n' "$master" >&2
  exit 1
fi

verified=0
for skill in "${skills[@]}"; do
  skill_root="$master/$skill"
  if [[ ! -f "$skill_root/SKILL.md" ]]; then
    printf 'ERROR: missing Skill entrypoint: %s\n' "$skill_root/SKILL.md" >&2
    exit 1
  fi

  expected=$(realpath "$skill_root")
  for base in "$HOME/.agents/skills" "$HOME/.claude/skills"; do
    link="$base/$skill"
    if [[ ! -e "$link" && ! -L "$link" ]]; then
      printf 'ERROR: missing symlink: %s\n' "$link" >&2
      exit 1
    fi
    if [[ ! -L "$link" ]]; then
      printf 'ERROR: not a symlink: %s\n' "$link" >&2
      exit 1
    fi
    actual=$(realpath "$link")
    if [[ "$actual" != "$expected" ]]; then
      printf 'ERROR: wrong target: %s -> %s (expected %s)\n' "$link" "$actual" "$expected" >&2
      exit 1
    fi
    verified=$((verified + 1))
  done
done

printf 'OK: verified %d links against %s\n' "$verified" "$master"
