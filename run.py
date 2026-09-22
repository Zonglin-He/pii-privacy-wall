import argparse
import os

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PII Privacy Wall · local-only application")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--dev-viewer", action="store_true", help="Expose masked captured HTTP payloads in the UI"
    )
    args = parser.parse_args()
    if args.dev_viewer:
        os.environ["PII_DEV_VIEWER"] = "1"
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
    )
