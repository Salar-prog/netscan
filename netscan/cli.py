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
