PAPERCLIP_DIR := references/paperclip
PAPERCLIP_ENV := PAPERCLIP_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1
# Tailscale hostname — change if different
HOMELAB_TS := homelab4change.siamese-dominant.ts.net

.DEFAULT_GOAL := help
.PHONY: help \
	nexus-start nexus-stop nexus-restart nexus-status nexus-logs nexus-health \
	nexus-api nexus-sync nexus-test nexus-test-integration \
	dashboard-dev \
	paperclip-install paperclip-start paperclip-stop \
	paperclip-dev paperclip-dev-once paperclip-server \
	paperclip-build paperclip-typecheck \
	paperclip-test paperclip-test-watch paperclip-test-e2e \
	paperclip-db-generate paperclip-db-migrate \
	paperclip-setup paperclip-setup-tailnet \
	install

# ─── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Nexus"
	@echo "  make nexus-start            Start daemon (foreground)"
	@echo "  make nexus-stop             Stop daemon"
	@echo "  make nexus-restart          Restart daemon"
	@echo "  make nexus-status           Show daemon status"
	@echo "  make nexus-logs             Tail logs"
	@echo "  make nexus-health           Health check"
	@echo "  make nexus-api              Start API server only (port 8200)"
	@echo "  make nexus-sync             Sync agent profiles to Atrium"
	@echo "  make nexus-test             Run unit tests"
	@echo "  make nexus-test-integration Run integration tests (needs Atrium)"
	@echo "  make dashboard-dev          Start dashboard SPA dev server (port 5273)"
	@echo ""
	@echo "Paperclip  (port 3100)"
	@echo "  First time:"
	@echo "  make paperclip-install      Install node deps (inside submodule)"
	@echo "  make paperclip-setup        Onboard locally (loopback, localhost:3100)"
	@echo "  make paperclip-setup-tailnet  Onboard on Tailscale → $(HOMELAB_TS):3100"
	@echo ""
	@echo "  Daily use:"
	@echo "  make paperclip-start        Start server (bound to configured host)"
	@echo "  make paperclip-stop         Stop server"
	@echo ""
	@echo "  Dev/source (run inside submodule, needs setup first):"
	@echo "  make paperclip-dev          pnpm dev  — full dev, watch mode"
	@echo "  make paperclip-dev-once     pnpm dev:once  — no file watching"
	@echo "  make paperclip-server       pnpm dev:server  — API only"
	@echo "  make paperclip-build        pnpm build"
	@echo "  make paperclip-typecheck    pnpm typecheck"
	@echo "  make paperclip-test         pnpm test  — Vitest only"
	@echo "  make paperclip-test-watch   pnpm test:watch"
	@echo "  make paperclip-test-e2e     pnpm test:e2e  — Playwright"
	@echo "  make paperclip-db-generate  pnpm db:generate"
	@echo "  make paperclip-db-migrate   pnpm db:migrate"
	@echo ""
	@echo "  make install                Install all deps (Nexus + dashboard + Paperclip)"
	@echo ""

# ─── Nexus ────────────────────────────────────────────────────────────────────

nexus-start:
	nexus start

nexus-stop:
	nexus stop

nexus-restart:
	nexus restart

nexus-status:
	nexus status

nexus-logs:
	nexus logs

nexus-health:
	nexus health

nexus-api:
	nexus api

nexus-sync:
	nexus sync-agents

nexus-test:
	pytest tests/ -m "not integration and not e2e" -q

nexus-test-integration:
	pytest tests/ -m "integration" -q

dashboard-dev:
	cd dashboard && pnpm dev

# ─── Paperclip — setup (runs from HOME, avoids git-worktree detection) ────────

# First-time setup: creates ~/.paperclip/instances/default/, starts server.
# After this, use paperclip-start / paperclip-stop.

paperclip-setup:
	cd ~ && $(PAPERCLIP_ENV) npx paperclipai onboard --yes
	@echo ""
	@echo "→ Paperclip running at http://localhost:3100"

paperclip-setup-tailnet:
	cd ~ && $(PAPERCLIP_ENV) npx paperclipai onboard --yes --bind tailnet
	@echo ""
	@echo "→ Paperclip running at http://$(HOMELAB_TS):3100"
	@echo "  Open that URL from your Mac browser."

# ─── Paperclip — daily run ────────────────────────────────────────────────────

paperclip-start:
	cd ~ && $(PAPERCLIP_ENV) npx paperclipai start

paperclip-stop:
	cd ~ && $(PAPERCLIP_ENV) npx paperclipai stop

# ─── Paperclip — source/dev (inside submodule) ───────────────────────────────

paperclip-install:
	cd $(PAPERCLIP_DIR) && pnpm install

paperclip-dev:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) pnpm dev

paperclip-dev-once:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) pnpm dev:once

paperclip-server:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) pnpm dev:server

paperclip-build:
	cd $(PAPERCLIP_DIR) && pnpm build

paperclip-typecheck:
	cd $(PAPERCLIP_DIR) && pnpm typecheck

paperclip-test:
	cd $(PAPERCLIP_DIR) && pnpm test

paperclip-test-watch:
	cd $(PAPERCLIP_DIR) && pnpm test:watch

paperclip-test-e2e:
	cd $(PAPERCLIP_DIR) && pnpm test:e2e

paperclip-db-generate:
	cd $(PAPERCLIP_DIR) && pnpm db:generate

paperclip-db-migrate:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) pnpm db:migrate

# ─── Install ──────────────────────────────────────────────────────────────────

install:
	uv sync
	cd dashboard && pnpm install
	cd $(PAPERCLIP_DIR) && pnpm install
