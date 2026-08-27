import click


@click.group()
def main():
    """NetScan - Production-grade IP discovery and availability platform."""


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind address.")
@click.option("--port", default=8000, type=int, help="Port to listen on.")
@click.option("--dashboard/--no-dashboard", default=True, help="Enable/disable the web dashboard.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
def serve(host, port, dashboard, reload):
    """Start the NetScan server."""
    from netscan.main import create_app

    app = create_app(dashboard=dashboard)
    import uvicorn

    uvicorn.run(app, host=host, port=port, reload=reload)


@main.command()
def login():
    """Authenticate via LDAP and create an API key for CLI/script use."""
    from netscan.config import settings

    if not settings.LDAP_ENABLED:
        click.echo("LDAP is not enabled. Set LDAP_ENABLED=true in your .env file.")
        return

    try:
        import ldap  # noqa: F401
    except ImportError:
        click.echo("python-ldap is not installed. Install with: pip install netscan[ldap]")
        return

    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True)

    from netscan.auth.ldap import ldap_authenticate, map_groups_to_role
    from netscan.api.auth import generate_api_key
    from netscan.db import get_session
    from netscan.models import ApiKey

    result = ldap_authenticate(username, password)
    if not result:
        click.echo("Authentication failed. Check your credentials or LDAP server availability.")
        return

    role = map_groups_to_role(result["groups"])
    click.echo(f"Authenticated as {result['username']} (role: {role.value})")

    raw_key, key_hash, prefix = generate_api_key()
    api_key_rec = ApiKey(
        name=f"cli-{result['username']}",
        key_hash=key_hash,
        prefix=prefix,
        role=role,
        is_active=True,
    )

    # Use the DB session from the generator
    session = next(get_session())
    try:
        session.add(api_key_rec)
        session.commit()
    except Exception:
        session.rollback()
        click.echo("Failed to create API key.")
        return
    finally:
        session.close()

    click.echo(f"\nAPI key created (role: {role.value}):\n")
    click.echo(f"  {raw_key}\n")
    click.echo("Store this key safely. It will never be shown again.")
    click.echo(f"\nUsage: export NETSCAN_API_KEY={raw_key}")
