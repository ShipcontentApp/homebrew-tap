"""Terminal access to ShipContent's Streamable HTTP MCP server."""

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.types import PaginatedRequestParams

from shipcontent_auth import Credentials, LoginRequired, browser_login, oauth_provider

VERSION = "0.1.1"
HOSTED = "https://mcp.shipcontent.com/mcp"


def endpoint(value):
    url = urlsplit(value)
    if (not url.hostname or url.username or url.password or url.query or url.fragment
            or not (url.scheme == "https" or
                    (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}))):
        raise argparse.ArgumentTypeError("Use an HTTPS MCP URL, or HTTP on loopback.")
    return value


def parse_args():
    parser = argparse.ArgumentParser(prog="shipcontent", description=__doc__)
    parser.add_argument("--version", action="version", version=f"shipcontent {VERSION}")
    parser.add_argument("--endpoint", type=endpoint, default=os.environ.get("SHIPCONTENT_MCP_URL", HOSTED))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="Sign in with your browser.")
    commands.add_parser("logout", help="Remove the local login from macOS Keychain.")
    commands.add_parser("status", help="List the workspaces this login can access.")
    commands.add_parser("tools", help="List the current tools and their input schemas as JSON.")
    call = commands.add_parser("call", help="Call an MCP tool once and print its JSON result.")
    call.add_argument("tool")
    call.add_argument("arguments", nargs="?", default="{}", help="A JSON object, or - for stdin.")
    args = parser.parse_args()
    if args.command == "call":
        try:
            args.arguments = json.loads(sys.stdin.read() if args.arguments == "-" else args.arguments)
        except ValueError:
            parser.error("Tool arguments must be valid JSON.")
        if not isinstance(args.arguments, dict):
            parser.error("Tool arguments must be a JSON object.")
    return args


async def run_session(args, auth):
    async with create_mcp_http_client(auth=auth) as http:
        async with streamable_http_client(args.endpoint, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if args.command == "login":
                    print("Signed in to ShipContent.")
                    return 0
                if args.command == "tools":
                    tools = []
                    params = None
                    while True:
                        page = await session.list_tools(params=params)
                        tools.extend(tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in page.tools)
                        if not page.next_cursor:
                            print(json.dumps(tools, ensure_ascii=False, indent=2))
                            return 0
                        params = PaginatedRequestParams(cursor=page.next_cursor)
                name = "list_workspaces" if args.command == "status" else args.tool
                arguments = {} if args.command == "status" else args.arguments
                result = await session.call_tool(name, arguments)
                print(result.model_dump_json(by_alias=True, exclude_none=True, indent=2))
                return int(result.is_error)


async def execute(args):
    # A refresh rotates a credential. Serialize processes for this endpoint,
    # including logout, so a late response cannot restore an old login.
    locks = Path.home() / "Library" / "Caches" / "ShipContent" / "cli"
    locks.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (locks / hashlib.sha256(args.endpoint.encode()).hexdigest()).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        credentials = Credentials(args.endpoint)
        if args.command == "logout":
            credentials.clear()
            print("Signed out on this Mac.")
            return 0
        if args.command == "login":
            async with browser_login() as browser:
                return await run_session(args, oauth_provider(credentials, browser))
        credentials.load()
        return await run_session(args, oauth_provider(credentials))


def failure_message(error):
    if isinstance(error, BaseExceptionGroup):
        return failure_message(error.exceptions[0])
    if isinstance(error, LoginRequired):
        return str(error)
    # Third-party HTTP exceptions can include an authorization URL or response.
    return f"ShipContent request failed ({type(error).__name__}). Check the endpoint and connection. Run shipcontent login to reconnect."


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        sys.exit(asyncio.run(execute(parse_args())))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        print(failure_message(error), file=sys.stderr)
        sys.exit(1)
