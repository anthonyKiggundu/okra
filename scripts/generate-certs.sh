#!/usr/bin/env bash
mkdir -p orchestrator/certs
openssl req -x509 -newkey rsa:2048 -nodes -keyout orchestrator/certs/server.key \
  -out orchestrator/certs/server.crt -days 365 -subj "/CN=localhost"

