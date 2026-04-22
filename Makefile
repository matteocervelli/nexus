PAPERCLIP_DIR := references/paperclip
PAPERCLIP_ENV := PAPERCLIP_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1

.DEFAULT_GOAL := help
.PHONY: help \
	nexus-start nexus-stop nexus-restart nexus-status nexus-logs nexus-health \
	nexus-api nexus-sync nexus-test nexus-test-integration \
	dashboard-dev \
	paperclip-install paperclip-dev paperclip-dev-once paperclip-server \
	paperclip-build paperclip-typecheck \
	paperclip-test paperclip-test-watch paperclip-test-e2e \
	paperclip-db-generate paperclip-db-migrate \
	paperclip-onboard paperclip-onboard-lan paperclip-onboard-tailnet \
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
	@echo "Paperclip  (references/paperclip, port 3100)"
	@echo "  make paperclip-install      pnpm install"
	@echo "  make paperclip-dev          pnpm dev  — API + UI, watch mode"
	@echo "  make paperclip-dev-once     pnpm dev:once  — no file watching"
	@echo "  make paperclip-server       pnpm dev:server  — API only"
	@echo "  make paperclip-build        pnpm build"
	@echo "  make paperclip-typecheck    pnpm typecheck"
	@echo "  make paperclip-test         pnpm test  — Vitest only"
	@echo "  make paperclip-test-watch   pnpm test:watch"
	@echo "  make paperclip-test-e2e     pnpm test:e2e  — Playwright"
	@echo "  make paperclip-db-generate  pnpm db:generate"
	@echo "  make paperclip-db-migrate   pnpm db:migrate"
	@echo "  make paperclip-onboard      npx paperclipai onboard (local loopback)"
	@echo "  make paperclip-onboard-lan  onboard --bind lan"
	@echo "  make paperclip-onboard-tailnet  onboard --bind tailnet"
	@echo ""
	@echo "  make install                Install deps for both Nexus and Paperclip"
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

# ─── Paperclip ────────────────────────────────────────────────────────────────

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

paperclip-onboard:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) npx paperclipai onboard --yes

paperclip-onboard-lan:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) npx paperclipai onboard --yes --bind lan

paperclip-onboard-tailnet:
	cd $(PAPERCLIP_DIR) && $(PAPERCLIP_ENV) npx paperclipai onboard --yes --bind tailnet

# ─── Install ──────────────────────────────────────────────────────────────────

install:
	uv sync
	cd dashboard && pnpm install
	cd $(PAPERCLIP_DIR) && pnpm install
