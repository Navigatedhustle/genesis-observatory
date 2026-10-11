#!/usr/bin/env bash
set -euo pipefail
systemctl --user stop genesis.service
echo 'Genesis stopped. Shared Ollama and unrelated services remain running.'
