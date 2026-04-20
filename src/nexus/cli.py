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


if __name__ == "__main__":
    cli()
