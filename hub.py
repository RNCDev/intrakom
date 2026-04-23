"""Hub entry point — run with: python hub.py [--port 8000]"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Intrakom hub server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000)")
    args = parser.parse_args()

    uvicorn.run(
        "intrakom.server:app",
        host="0.0.0.0",
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
