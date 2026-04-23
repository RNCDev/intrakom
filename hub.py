"""Hub entry point — run with: python hub.py [--port 8000] [--cert cert.crt --key cert.key]"""
import argparse
import os
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Intrakom hub server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000)")
    parser.add_argument("--cert", help="TLS certificate file (enables HTTPS)")
    parser.add_argument("--key", help="TLS private key file")
    args = parser.parse_args()

    # Auto-detect Tailscale cert if present alongside hub.py
    cert = args.cert
    key = args.key
    if not cert:
        for f in os.listdir("."):
            if f.endswith(".crt"):
                candidate_key = f.replace(".crt", ".key")
                if os.path.exists(candidate_key):
                    cert, key = f, candidate_key
                    break

    kwargs = dict(
        app="intrakom.server:app",
        host="0.0.0.0",
        port=args.port,
        reload=False,
    )
    if cert and key:
        kwargs["ssl_certfile"] = cert
        kwargs["ssl_keyfile"] = key
        os.environ["INTRAKOM_SCHEME"] = "https"
    else:
        os.environ["INTRAKOM_SCHEME"] = "http"

    os.environ["INTRAKOM_PORT"] = str(args.port)
    uvicorn.run(**kwargs)


if __name__ == "__main__":
    main()
