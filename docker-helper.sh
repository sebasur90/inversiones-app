#!/bin/bash
# Docker Compose Helper - Local vs Corporate

set -e

USAGE="
Usage: $0 [local|corporate] [command]

Commands:
  local up         - Start project without proxy
  local down       - Stop project (local)
  local logs       - View logs (local)
  local build      - Build images (local)

  corporate up     - Start project with corporate proxy
  corporate down   - Stop project (corporate)
  corporate logs   - View logs (corporate)
  corporate build  - Build images with corporate proxy

Examples:
  $0 local up
  $0 corporate build
  $0 corporate logs
"

if [ $# -lt 2 ]; then
    echo "$USAGE"
    exit 1
fi

ENV=$1
CMD=$2
shift 2

case $ENV in
    local)
        echo "🚀 Using LOCAL configuration (no proxy)"
        docker compose $CMD "$@"
        ;;
    corporate)
        if [ ! -f ".env.corporate" ]; then
            echo "❌ Error: .env.corporate not found"
            echo ""
            echo "Create .env.corporate from template:"
            echo "  cp .env.example .env.corporate"
            echo "  # Edit .env.corporate with your proxy details"
            exit 1
        fi
        echo "🏢 Using CORPORATE configuration (with proxy)"
        docker compose -f docker-compose.yml -f docker-compose.corporate.yml --env-file .env.corporate $CMD "$@"
        ;;
    *)
        echo "❌ Invalid environment: $ENV"
        echo "$USAGE"
        exit 1
        ;;
esac
