"""Browser sign-in and endpoint-scoped macOS Keychain storage for the MCP SDK."""

import asyncio
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from keyring.backends.macOS import Keyring
from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthMetadata, OAuthToken

SERVICE = "com.shipcontent.cli.oauth"


class LoginRequired(Exception):
    pass


class Credentials:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.keychain = Keyring()
        self.saved = {}
        self.client = None
        self.provider = None

    def load(self):
        record = self.keychain.get_password(SERVICE, self.endpoint)
        if not record:
            raise LoginRequired("Run shipcontent login to connect this Mac.")
        self.saved = json.loads(record)
        self.client = OAuthClientInformationFull.model_validate(self.saved["client"])

    def clear(self):
        if self.keychain.get_password(SERVICE, self.endpoint) is not None:
            self.keychain.delete_password(SERVICE, self.endpoint)

    async def get_tokens(self):
        if "tokens" in self.saved:
            return OAuthToken.model_validate(self.saved["tokens"])

    async def get_client_info(self):
        return self.client

    async def set_client_info(self, client):
        # Save the new registration only after the owner completes login.
        self.client = client

    async def set_tokens(self, tokens):
        data = tokens.model_dump(mode="json")
        if not data.get("refresh_token") and self.saved.get("tokens"):
            data["refresh_token"] = self.saved["tokens"].get("refresh_token")
        ctx = self.provider.context
        self.saved = {
            "tokens": data,
            "client": self.client.model_dump(mode="json"),
            "metadata": ctx.oauth_metadata.model_dump(mode="json"),
            "expires": time.time() + tokens.expires_in if tokens.expires_in is not None else None,
        }
        self.keychain.set_password(SERVICE, self.endpoint, json.dumps(self.saved))


class Callback(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # The callback URL contains a single-use authorization code.

    def do_GET(self):
        url = urlsplit(self.path)
        params = parse_qs(url.query)
        if url.path != "/callback" or params.get("state") != [self.server.expected_state]:
            self.send_error(400)
            return
        self.server.callback = params
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"Return to the ShipContent CLI to finish.")


class Browser:
    def __init__(self, server):
        self.server = server
        self.redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"

    async def open(self, url):
        self.server.expected_state = parse_qs(urlsplit(url).query)["state"][0]
        if not webbrowser.open(url):
            raise LoginRequired("Could not open a browser. Set the default browser and run shipcontent login again.")

    async def receive(self):
        deadline = time.monotonic() + 300
        self.server.callback = None
        while self.server.callback is None:
            if time.monotonic() >= deadline:
                raise LoginRequired("Sign-in timed out. Run shipcontent login again.")
            await asyncio.to_thread(self.server.handle_request)
        params = self.server.callback
        if "error" in params:
            raise LoginRequired("Sign-in was declined. Run shipcontent login to try again.")
        return AuthorizationCodeResult(code=params["code"][0], state=params["state"][0], iss=params.get("iss", [None])[0])


@asynccontextmanager
async def browser_login():
    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        yield Browser(server)


async def require_login(*_):
    raise LoginRequired("Your login needs attention. Run shipcontent login to reconnect.")


def oauth_provider(credentials, browser=None):
    redirect = browser.redirect_uri if browser else str(credentials.client.redirect_uris[0])
    metadata = OAuthClientMetadata(client_name="ShipContent CLI", redirect_uris=[redirect],
                                   grant_types=["authorization_code", "refresh_token"],
                                   response_types=["code"], token_endpoint_auth_method="none",
                                   scope="mcp:access offline_access")
    provider = OAuthClientProvider(credentials.endpoint, metadata, credentials,
                                  browser.open if browser else require_login,
                                  browser.receive if browser else require_login)
    credentials.provider = provider
    if credentials.saved:
        # Across CLI processes, restore the issuer's actual token endpoint
        # and the absolute expiry before the SDK attempts a refresh.
        ctx = provider.context
        ctx.oauth_metadata = OAuthMetadata.model_validate(credentials.saved["metadata"])
        ctx.auth_server_url = str(ctx.oauth_metadata.issuer)
        ctx.token_expiry_time = credentials.saved["expires"]
    return provider
