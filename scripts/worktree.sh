#!/bin/bash
# Worktree management for multi-agent development
# Usage:
#   ./scripts/worktree.sh create <task-name>    — create branch + worktree
#   ./scripts/worktree.sh cleanup <task-name>   — merge, remove worktree, delete branch
#   ./scripts/worktree.sh list                  — list active worktrees
#   ./scripts/worktree.sh abort <task-name>     — remove worktree without merging

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$(dirname "$REPO_ROOT")"

cmd="${1:-help}"
task="${2:-}"

case "$cmd" in
  create)
    if [ -z "$task" ]; then
      echo "Usage: $0 create <task-name>"
      exit 1
    fi
    branch="feature/${task}"
    worktree="${PARENT_DIR}/trading-bots-${task}"
    
    cd "$REPO_ROOT"
    git fetch origin
    git worktree add "$worktree" -b "$branch"
    echo "Created worktree: $worktree"
    echo "Branch: $branch"
    echo "cd $worktree"
    ;;

  cleanup)
    if [ -z "$task" ]; then
      echo "Usage: $0 cleanup <task-name>"
      exit 1
    fi
    branch="feature/${task}"
    worktree="${PARENT_DIR}/trading-bots-${task}"
    
    cd "$REPO_ROOT"
    git checkout main
    git pull origin main
    
    # Merge
    echo "Merging $branch into main..."
    git merge "$branch" --no-edit
    git push origin main
    
    # Cleanup
    echo "Removing worktree..."
    git worktree remove "$worktree" --force 2>/dev/null || rm -rf "$worktree"
    git branch -d "$branch" 2>/dev/null || git branch -D "$branch"
    git push origin --delete "$branch" 2>/dev/null || true
    
    echo "Done! Branch $branch merged and cleaned up."
    ;;

  abort)
    if [ -z "$task" ]; then
      echo "Usage: $0 abort <task-name>"
      exit 1
    fi
    branch="feature/${task}"
    worktree="${PARENT_DIR}/trading-bots-${task}"
    
    cd "$REPO_ROOT"
    echo "Removing worktree without merge..."
    git worktree remove "$worktree" --force 2>/dev/null || rm -rf "$worktree"
    git branch -D "$branch" 2>/dev/null || true
    git push origin --delete "$branch" 2>/dev/null || true
    
    echo "Aborted. Worktree and branch removed."
    ;;

  list)
    cd "$REPO_ROOT"
    echo "Active worktrees:"
    git worktree list
    echo ""
    echo "Feature branches:"
    git branch | grep "feature/" || echo "  (none)"
    ;;

  *)
    echo "Usage: $0 {create|cleanup|abort|list} [task-name]"
    echo ""
    echo "Commands:"
    echo "  create  <task>  — create branch + worktree"
    echo "  cleanup <task>  — merge to main, remove worktree"
    echo "  abort   <task>  — remove worktree without merge"
    echo "  list            — show active worktrees"
    ;;
esac
