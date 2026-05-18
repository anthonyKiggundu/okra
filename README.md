# okra

Stateful/context inter-slice migration orchestrator for a 5G control plane.

## What is implemented

- Session-scoped migration lifecycle (`prepared -> transferring -> committed/rolled_back`)
- Context transfer progress tracking with commit gating at 100%
- Rollback handling for interrupted migrations
- Event history per session for control-plane observability

## Quick test

```bash
python -m unittest discover -s tests -v
```
