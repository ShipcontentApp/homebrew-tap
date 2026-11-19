# ShipContent CLI

Use ShipContent MCP tools from the terminal on an Apple Silicon Mac. Homebrew installs the CLI and its Python runtime.

## Install

```sh
brew install shipcontentapp/tap/shipcontent
shipcontent --version
```

For the short command on Homebrew versions with tap trust, register the tap and trust its formula once:

```sh
brew tap shipcontentapp/tap
brew trust --formula shipcontentapp/tap/shipcontent
brew install shipcontent
```

## Connect and use the CLI

```sh
shipcontent login
shipcontent status
shipcontent tools
shipcontent call list_workspaces
```

Login opens your browser for sign-in and consent. The CLI saves its credentials in macOS Keychain. Status shows the workspaces available to your login. The tools command returns the current tool names and input schemas.

Use an MCP tool name and pass its arguments as a JSON object. Pass `-` in place of the JSON object to read it from stdin. Calls print the MCP result as JSON and return a nonzero exit code on a tool error.

Run `shipcontent logout` to remove the local credentials for the selected endpoint. The default endpoint is `https://mcp.shipcontent.com/mcp`. To use a local server, set `SHIPCONTENT_MCP_URL` or pass `--endpoint` before the command. Credentials are stored separately for each endpoint.

## Updates

```sh
brew update
brew upgrade shipcontentapp/tap/shipcontent
```

Find the versioned archive and checksum in [Releases](https://github.com/ShipcontentApp/homebrew-tap/releases). To reproduce the archive, run `python3.14 scripts/package.py dist` in a checkout of its tag on an Apple Silicon Mac. The package includes the CLI source and dependency wheels verified against the hashes in `cli/requirements.txt`.
