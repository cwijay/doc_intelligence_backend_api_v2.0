#!/usr/bin/env python3
"""
OpenAPI Client Generation Script for Document Intelligence Backend.

Generates TypeScript client types from the FastAPI OpenAPI schema using openapi-typescript.

Usage:
    # Generate TypeScript types (default output to Next.js app)
    uv run python scripts/generate_client.py

    # Custom output path
    uv run python scripts/generate_client.py --output ../my-nextjs-app/src/types/api.d.ts

    # Custom server URL
    uv run python scripts/generate_client.py --server-url http://localhost:8080

    # Preview without generating
    uv run python scripts/generate_client.py --dry-run

Requirements:
    - Node.js with npx (for openapi-typescript)
    - Running dev server (./deploy.sh --dev)
"""

import argparse
import logging
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "doc_intelligence_frontend" / "src" / "types" / "api.d.ts"
DEFAULT_SERVER_URL = "http://localhost:8000"
OPENAPI_PATH = "/api/v1/openapi.json"


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def colored(text: str, color: str) -> str:
    """Wrap text with ANSI color codes."""
    return f"{color}{text}{Colors.END}"


def check_npx_available() -> bool:
    """Check if npx is available in PATH."""
    try:
        result = subprocess.run(
            ["npx", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_server_running(server_url: str) -> bool:
    """Check if the dev server is running by hitting the health endpoint."""
    health_url = f"{server_url}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def fetch_openapi_schema(server_url: str) -> bool:
    """Verify the OpenAPI schema is accessible."""
    schema_url = f"{server_url}{OPENAPI_PATH}"
    try:
        with urllib.request.urlopen(schema_url, timeout=10) as response:
            if response.status == 200:
                # Verify it's valid JSON by reading it
                response.read()
                return True
            return False
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def generate_typescript_client(
    server_url: str, output_path: Path, dry_run: bool = False
) -> bool:
    """Generate TypeScript types using openapi-typescript."""
    schema_url = f"{server_url}{OPENAPI_PATH}"

    # Ensure output directory exists
    output_dir = output_path.parent
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Schema URL: {colored(schema_url, Colors.BLUE)}")
    logger.info(f"Output path: {colored(str(output_path), Colors.BLUE)}")

    if dry_run:
        logger.info(colored("Dry run - skipping generation", Colors.YELLOW))
        return True

    # Run openapi-typescript
    cmd = ["npx", "openapi-typescript", schema_url, "-o", str(output_path)]
    logger.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(PROJECT_ROOT),
        )

        if result.returncode == 0:
            logger.info(colored("TypeScript types generated successfully!", Colors.GREEN))
            if result.stdout:
                logger.info(result.stdout)
            return True
        else:
            logger.error(colored("Generation failed!", Colors.RED))
            if result.stderr:
                logger.error(result.stderr)
            if result.stdout:
                logger.error(result.stdout)
            return False

    except FileNotFoundError:
        logger.error(colored("npx not found. Please install Node.js.", Colors.RED))
        return False
    except Exception as e:
        logger.error(colored(f"Unexpected error: {e}", Colors.RED))
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate TypeScript client types from OpenAPI schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Generate with defaults
  %(prog)s --output ./types/api.d.ts          # Custom output path
  %(prog)s --server-url http://localhost:8080 # Custom server
  %(prog)s --dry-run                          # Preview without generating
        """,
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path for generated types (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--server-url",
        type=str,
        default=DEFAULT_SERVER_URL,
        help=f"Dev server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without generating",
    )

    args = parser.parse_args()

    print(colored("\n=== OpenAPI Client Generator ===\n", Colors.BOLD))

    # Step 1: Check npx is available
    logger.info("Checking for npx...")
    if not check_npx_available():
        logger.error(
            colored(
                "npx is not available. Please install Node.js: https://nodejs.org/",
                Colors.RED,
            )
        )
        sys.exit(1)
    logger.info(colored("npx found", Colors.GREEN))

    # Step 2: Check server is running
    logger.info(f"Checking if server is running at {args.server_url}...")
    if not check_server_running(args.server_url):
        logger.error(
            colored(
                f"\nServer is not running at {args.server_url}",
                Colors.RED,
            )
        )
        logger.error(
            colored(
                "\nPlease start the dev server first:\n"
                "  ./deploy.sh --dev\n"
                "or:\n"
                "  uv run uvicorn app.main:app --reload --reload-dir app",
                Colors.YELLOW,
            )
        )
        sys.exit(1)
    logger.info(colored("Server is running", Colors.GREEN))

    # Step 3: Verify OpenAPI schema is accessible
    logger.info("Verifying OpenAPI schema is accessible...")
    if not fetch_openapi_schema(args.server_url):
        logger.error(
            colored(
                f"\nCould not fetch OpenAPI schema from {args.server_url}{OPENAPI_PATH}",
                Colors.RED,
            )
        )
        logger.error(
            colored(
                "\nMake sure DEBUG=True is set (OpenAPI is only exposed in debug mode)",
                Colors.YELLOW,
            )
        )
        sys.exit(1)
    logger.info(colored("OpenAPI schema accessible", Colors.GREEN))

    # Step 4: Generate TypeScript types
    logger.info("\nGenerating TypeScript types...")
    success = generate_typescript_client(
        server_url=args.server_url,
        output_path=args.output,
        dry_run=args.dry_run,
    )

    if success:
        print(colored("\n=== Generation Complete ===\n", Colors.BOLD + Colors.GREEN))
        if not args.dry_run:
            logger.info(f"Types written to: {colored(str(args.output), Colors.BLUE)}")
            logger.info(
                colored(
                    "\nUsage in your Next.js app:\n"
                    '  import type { paths, components } from "@/types/api";\n',
                    Colors.YELLOW,
                )
            )
        sys.exit(0)
    else:
        print(colored("\n=== Generation Failed ===\n", Colors.BOLD + Colors.RED))
        sys.exit(1)


if __name__ == "__main__":
    main()
