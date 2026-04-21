"""Nexus daemon CLI entry points."""

from __future__ import annotations

import asyncio

import click

from nexus.daemon import NexusDaemon


@click.group()
def cli() -> None:
    pass


@cli.command()
def start() -> None:
    """Start the Nexus daemon."""
    asyncio.run(NexusDaemon().start())


@cli.command()
def health() -> None:
    """Check daemon health (placeholder)."""
    click.echo("nexus: ok")


@cli.command("sync-agents")
@click.option("--agents-dir", default="agents/", show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--atrium-url", default=None)
def sync_agents(agents_dir: str, dry_run: bool, atrium_url: str | None) -> None:
    """Upsert agent profiles from CLAUDE.md files into Atrium agent_registry."""
    import os
    import pathlib

    import httpx

    from nexus.agent_loader import load_agent_profiles

    base_url = atrium_url or os.environ.get("ATRIUM_URL", "http://localhost:8100")
    agents_path = pathlib.Path(agents_dir)

    try:
        profiles = load_agent_profiles(agents_path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if not profiles:
        click.echo("No agent profiles found.")
        return

    click.echo(f"{'agent_role':<25} {'status':<10} {'timeout':>8} {'budget':>12}")
    click.echo("-" * 60)

    for p in profiles:
        if dry_run:
            click.echo(
                f"{p.agent_role:<25} {'dry-run':<10} {p.timeout_seconds:>8} {p.monthly_token_budget:>12}"
            )
            continue

        payload = {
            "agent_role": p.agent_role,
            "execution_backend": p.execution_backend,
            "model": p.model,
            "capability_class": p.capability_class,
            "profile_path": p.profile_path,
            "tool_allowlist": p.tool_allowlist,
            "timeout_seconds": p.timeout_seconds,
            "monthly_token_budget": p.monthly_token_budget,
            "is_active": p.is_active,
        }
        try:
            resp = httpx.post(f"{base_url}/api/agent_registry", json=payload, timeout=10)
            resp.raise_for_status()
            status = "upserted"
        except httpx.HTTPError as exc:
            status = f"ERROR: {exc}"

        click.echo(
            f"{p.agent_role:<25} {status:<10} {p.timeout_seconds:>8} {p.monthly_token_budget:>12}"
        )


if __name__ == "__main__":
    cli()
