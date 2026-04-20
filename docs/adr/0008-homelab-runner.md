# ADR-0008 — Homelab as Primary Agent Runner

Date: 2026-04-20
Status: Accepted

## Context

Three deployment targets were evaluated for the Nexus daemon:

- **Mac Studio (local workstation)** — primary development machine, always available, high-spec hardware
- **AX42 (Hetzner VPS)** — production infrastructure host for deployed adlimen services
- **Homelab** (`homelab4change.siamese-dominant.ts.net`) — dedicated always-on machine on the local network, accessible via Tailscale

The daemon spawns agent subprocesses that consume meaningful CPU and memory for the duration of each task. Deployment target matters.

## Decision

The Nexus daemon runs on **homelab** as Phase 1 primary agent runner.

Deployment details:

- Nexus daemon deployed as a `systemd` service or `launchd` agent on the homelab host
- Communication to Atrium and Limen over Tailscale (no public exposure required)
- Remote triggering path: Limen Telegram command → Atrium `work_item` → homelab Nexus daemon picks it up on next heartbeat
- No artificial parallel agent limit — homelab has dedicated resources not shared with interactive dev work

## Rationale

1. **Mac Studio conflicts with interactive development.**
   Agent subprocesses (Claude Code CLI, Codex CLI) are CPU and RAM intensive. Running them on the primary workstation during an active development session degrades the developer experience and introduces resource contention.

2. **AX42 is production infrastructure.**
   AX42 hosts deployed adlimen services. It is not appropriate for spawning AI agent subprocesses, which are experimental, long-running, and may consume unpredictable resources. Mixing orchestration experiments with production services introduces operational risk.

3. **Homelab is the right isolation boundary.**
   A dedicated machine provides resource isolation, always-on availability, and full control without production risk. Tailscale makes it reachable from anywhere without port forwarding or public exposure.

4. **Phase 2 extends, not replaces.**
   Phase 2 (Mac Mini M4 as dedicated runner) is an extension of this model. The homelab runner pattern established here carries forward directly.

## Consequences

- Daemon startup, deployment, and `update` target the homelab host
- `nexus doctor` command must verify homelab reachability over Tailscale and confirm Atrium is accessible from the homelab host
- Subprocess orphan cleanup is critical: if the daemon crashes on homelab, spawned agent PIDs become orphans on that machine. `os.killpg` on a process group, combined with a startup orphan scan, is the mitigation.
- Logs are on homelab; `nexus logs` must support remote log tailing (e.g. via SSH or a log forwarding setup)
- Phase 2 migration path: extend the spawner to SSH-dispatch to Mac Mini M4 when it is provisioned

## References

- [Nexus Vision](../development/nexus-vision.md)
