# Nexus Dashboard

Observability SPA for the Nexus orchestration daemon — workflow feed, agent status, audit log.

Stack: React 19 + Vite 6 + TanStack Router/Query + `@adlimen/ui-react`.

```bash
# FORGEJO_NPM_TOKEN must be set to resolve @adlimen/ui-react from the private registry.
# Obtain your token from https://git.adlimen.dev/user/settings/applications
export FORGEJO_NPM_TOKEN=<your-token>
pnpm install
pnpm dev        # http://localhost:5273
pnpm build      # dist/
```

> **Note**: This app lives temporarily in the `nexus` Python repo. Planned to move to
> `atrium/apps/nexus-dashboard/` once the Atrium infra alignment is complete.
