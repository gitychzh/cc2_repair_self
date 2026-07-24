# cc2_repair_self gateway backup

This repo holds **snapshot backups of the live gateway source** under `/opt/cc-infra/proxy/`
on HM2 (100.109.57.26). Purpose: provide a **rollback anchor** before experimental
gateway changes driven by the cc2 self-optimizer.

## Tag policy

Tags named `cc_sN` mark "checkpoint N" — the known-good state before an experiment.
To roll back an experiment: copy the files from the tagged snapshot back to
`/opt/cc-infra/proxy/<svc>/gateway/` and `docker compose up -d <svc>`.

- `cc_s2` — baseline before the "stepped-timeout (120->180->240s) + heartbeat" experiment.
  Captured: nv-gw/cc4101/ms-gw gateway/*.py + Dockerfile + docker-compose.yml + nv_gw env.
  Date: 2026-07-24. State: NVU_GLM52_EXP_BACKOFF=0 (off), TIER_BUDGET_GLM5_2_NV=120,
  ABSOLUTE_CAP_S=150, UPSTREAM_TIMEOUT=66. R1927 exp-backoff code exists but disabled.

## Layout
- `gateway_backup/nv-gw/` — NV gateway source (optimization target)
- `gateway_backup/cc4101/` — CC adapter (anthropic<->openai, heartbeat candidate)
- `gateway_backup/ms-gw/` — MS gateway (fallback)
- `gateway_backup/docker-compose.yml.HM2` — live compose env
- `gateway_backup/nv_gw_env.HM2.txt` — runtime env snapshot
