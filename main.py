"""Entry point — run the CLI or start the API server."""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        import uvicorn
        host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
        uvicorn.run("jarvis.api:app", host=host, port=port, reload=True)
    else:
        from jarvis.cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
