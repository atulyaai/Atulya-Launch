"""
Atulya-Launch entry point for `python -m atulya_launch`.

Usage:
    python -m atulya_launch --web [--port PORT] [--host HOST]
    python -m atulya_launch --help
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="atulya-launch",
        description="Atulya-Launch — Lightweight cPanel alternative",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=False,
        help="Start the web control panel server",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host/IP to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8443,
        help="Port to listen on (default: 8443)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('atulya_launch').__version__}",
    )

    args = parser.parse_args()

    if args.web:
        try:
            from atulya_launch.web.app import create_app
            app = create_app()
            import uvicorn
            uvicorn.run(
                app,
                host=args.host,
                port=args.port,
                log_level="info",
                access_log=True,
            )
        except ImportError as e:
            print(f"Error: Missing web dependencies. Install with: pip install atulya-launch[web]", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            sys.exit(0)
    else:
        from atulya_launch.cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
