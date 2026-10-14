"""The MCP server catalog (.agents/mcp-servers.json) and how each client sees it.

One definition per server, rendered for each client: Claude Code expands `${NAME:-default}` in
its config, so a machine can override a default by exporting the variable; Codex expands
nothing and passes servers a filtered environment, so it gets literal values. Pinned npx servers
run with `npm_config_before` at their pin's date and a cache of their own, so the cooldown holds
for their dependencies on a first install too. Servers are keyless and read-only: no headers, no
tokens, nothing that widens what a client may do.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

MCP_SERVERS_NAME = "mcp-servers.json"
SERVER_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")  # a TOML bare key and a Claude name too
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
TOOL_NAME = re.compile(r"[A-Za-z0-9_.-]+")
SECRET_NAME = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|PRIVATE|AUTH|BEARER|SESSION|COOKIE"
    r"|(?:^|_)PAT(?:_|$)",
    re.I,
)
SECRET_FLAG = re.compile(
    r"^--?[\w-]*(token|secret|passw|credential|api[-_]?key|private[-_]?key|auth|bearer|cookie)",
    re.I,
)
SECRET_VALUE = re.compile(r"^(hf_|sk-|ghp_|gho_|github_pat_|xox[abpr]-|AKIA|AIza|glpat-)")
NOT_SECRET = {  # names that look secret but only choose something, with the values they take
    "AZURE_TOKEN_CREDENTIALS": {  # the Azure Identity credential type (casefolded)
        "dev", "prod", "environmentcredential", "workloadidentitycredential",
        "managedidentitycredential", "azureclicredential", "azurepowershellcredential",
        "azuredeveloperclicredential", "visualstudiocodecredential",
    },
}  # fmt: skip
FLAG = re.compile(r"--[a-z0-9][a-z0-9-]*")
UV_PINNED = re.compile(r"[A-Za-z0-9._-]+(?:\[[A-Za-z0-9,._-]+\])?")  # a package, extras allowed
PACK_KEYS = {"description", "skills", "mcp"}
REF_KEYS = {"server", "args"}
REGISTRY = {"npx": "npm", "uvx": "pypi"}
CACHE = "{cache}"  # in args: the machine's repo-template cache folder
FORBIDDEN_ARGS = {
    "--dangerously-disable-elicitation",
    "--allow-unrestricted-file-access",
    "--outgoing-auth-strategy",
}
FORBIDDEN_PREFIXES = ("--dangerously-", "--insecure-")  # every flag that says it widens access
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
MACHINE_ENV = {"AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_CLIENT_ID"}  # set by each machine
MACHINE_FLAGS = {"--tenant", "--tenant-id", "--subscription", "--subscription-id"}
SERVER_KEYS = {
    "scope",
    "clients",
    "command",
    "args",
    "url",
    "env",
    "pin",
    "codex",
    "deny",
    "source",
    "why",
    "packArgs",
}
CODEX_KEYS = {"startup_timeout_sec", "tool_timeout_sec", "enabled_tools"}
PIN_KEYS = {"registry", "package", "version", "publishedAt", "pinException"}
CLIENTS = {"claude", "codex"}
MAX_TOOL_NAME = 64  # Claude Code's limit on mcp__<server>__<tool>


@dataclass(frozen=True)
class Pin:
    registry: Literal["npm", "pypi"]
    package: str
    version: str
    published_at: str
    exception: str | None = None


@dataclass(frozen=True)
class Server:
    name: str
    scope: Literal["global", "pack"]
    clients: frozenset[str]
    command: str | None
    args: tuple[str, ...]
    url: str | None
    env: Mapping[str, str]
    pin: Pin | None
    deny: tuple[str, ...]
    startup_timeout_sec: float | None = None
    tool_timeout_sec: float | None = None
    enabled_tools: tuple[str, ...] | None = None
    source: str = ""
    why: str = ""
    pack_args: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    pack_flags: tuple[str, ...] = ()  # the flags a pack may add (packArgs)


def _fail(path: Path, where: str, message: str) -> ValueError:
    return ValueError(f"{path}: {where}: {message}")


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _printable(value: str) -> bool:
    return all(char.isprintable() for char in value)


def _pin(path: Path, name: str, raw: Any) -> Pin | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - PIN_KEYS:
        raise _fail(path, name, f"'pin' takes {sorted(PIN_KEYS)}")
    if raw.get("registry") not in {"npm", "pypi"}:
        raise _fail(path, name, "'pin.registry' is npm or pypi")
    for key in ("package", "version", "publishedAt"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise _fail(path, name, f"'pin.{key}' is required")
    try:
        published = datetime.fromisoformat(raw["publishedAt"].replace("Z", "+00:00"))
    except ValueError:
        raise _fail(path, name, "'pin.publishedAt' is an ISO-8601 time") from None
    if published.tzinfo is None:
        raise _fail(path, name, "'pin.publishedAt' needs a time zone (end it in Z)")
    exception = raw.get("pinException")
    if exception is not None and (not isinstance(exception, str) or not exception.strip()):
        raise _fail(path, name, "'pin.pinException' needs a reason")
    return Pin(raw["registry"], raw["package"], raw["version"], raw["publishedAt"], exception)


COOLDOWN = timedelta(days=7)  # how old a release must be before it is pinned


def cooldown_problem(server: Server, now: datetime) -> str | None:
    """Why a server's pin can't be used yet: published in the future, or less than COOLDOWN
    old without a pinException saying why."""
    pin = server.pin
    if pin is None:
        return None
    published = datetime.fromisoformat(pin.published_at.replace("Z", "+00:00"))
    if published > now:
        return f"MCP server {server.name}: its pin's publishedAt is in the future"
    if now - published < COOLDOWN and not pin.exception:
        return (
            f"MCP server {server.name}: {pin.package}@{pin.version} is less than "
            f"{COOLDOWN.days} days old; pin an older release, or give the pin a pinException "
            f"saying why"
        )
    return None


def usable(servers: Mapping[str, Server], now: datetime, errors: list[str]) -> dict[str, Server]:
    """The servers whose pins may run now; each one held back is reported in errors."""
    kept = {}
    for name, server in servers.items():
        problem = cooldown_problem(server, now)
        if problem:
            errors.append(f"{problem}; not installed")
        else:
            kept[name] = server
    return kept


def _secret_arg(value: str) -> bool:
    return bool(SECRET_FLAG.match(value) or SECRET_VALUE.match(value))


def _check_arg(path: Path, where: str, value: str) -> None:
    """Refuse an argument that is a placeholder, a secret, a machine's own Azure ID, or one
    that widens access."""
    if not _printable(value) or "${" in value:
        raise _fail(path, where, f"{value!r}: no placeholders or control characters")
    flag = value.split("=", 1)[0]
    if flag in FORBIDDEN_ARGS or flag.startswith(FORBIDDEN_PREFIXES):
        raise _fail(path, where, f"{value} is never allowed")
    if flag in MACHINE_FLAGS or GUID.search(value):
        raise _fail(path, where, f"{value!r}: tenant, subscription and client IDs belong to each "
                    f"machine (az login or its environment), not the catalog")  # fmt: skip
    if _secret_arg(value):
        raise _fail(path, where, f"{value!r}: servers are keyless; no secrets in args")


def _check_args(path: Path, where: str, args: Sequence[str]) -> None:
    """The arguments one by one, then together: --read-only takes no value, and --transport
    only stdio (a server reached over HTTP would listen on a port)."""
    for value in args:
        _check_arg(path, where, value)
    for index, value in enumerate(args):
        following = args[index + 1] if index + 1 < len(args) else None
        if value.startswith("--read-only="):
            raise _fail(path, where, "--read-only takes no value")
        if value == "--read-only" and following is not None and not following.startswith("-"):
            raise _fail(path, where, "--read-only takes no value")
        if value.split("=", 1)[0] == "--transport":
            chosen = value.split("=", 1)[1] if "=" in value else following
            if chosen != "stdio":
                raise _fail(path, where, "--transport is stdio only")


def runs_pin(command: str, args: Sequence[str], pin: Pin) -> bool:
    """Whether the args run exactly the pinned package: for npx its first positional argument
    is package@version (no --package, which would run another); for uvx, `--from
    package==version <tool>` or `package==version` / `package@version` first, so no uv option
    (--with, --index, --exclude-newer) comes before it."""
    if command == "npx":
        if any(arg in {"-p", "--package"} or arg.startswith("--package=") for arg in args):
            return False
        first = next((arg for arg in args if not arg.startswith("-")), None)
        return first == f"{pin.package}@{pin.version}"
    if command == "uvx":
        if not UV_PINNED.fullmatch(pin.package):
            return False
        if list(args[:2]) == ["--from", f"{pin.package}=={pin.version}"]:
            return len(args) > 2 and not args[2].startswith("-")
        return list(args[:1]) in (
            [f"{pin.package}=={pin.version}"],
            [f"{pin.package}@{pin.version}"],
        )
    return False


def _server(path: Path, name: str, raw: Any) -> Server:
    if not SERVER_NAME.fullmatch(name):
        raise _fail(path, name, "a server name is lowercase letters, digits and hyphens")
    if not isinstance(raw, dict):
        raise _fail(path, name, "a server is an object")
    unknown = set(raw) - SERVER_KEYS
    if unknown:  # Codex ignores unknown keys silently, so a typo here would go unnoticed
        raise _fail(path, name, f"unknown keys {sorted(unknown)}")
    scope = raw.get("scope")
    if scope not in {"global", "pack"}:
        raise _fail(path, name, "'scope' is global or pack")
    clients = raw.get("clients", sorted(CLIENTS))
    if not _strings(clients) or not clients or set(clients) - CLIENTS:
        raise _fail(path, name, "'clients' lists claude and/or codex")
    command, url = raw.get("command"), raw.get("url")
    if (command is None) == (url is None):
        raise _fail(path, name, "a server has exactly one of 'command' and 'url'")
    args = raw.get("args", [])
    if not _strings(args) or (url is not None and args):
        raise _fail(path, name, "'args' is a list of strings, for a command only")
    if command is not None and (
        not isinstance(command, str) or not re.fullmatch(r"[\w.-]+", command)
    ):
        raise _fail(path, name, "'command' is a program name")
    if url is not None:
        parts = urllib.parse.urlsplit(url) if isinstance(url, str) else None
        if parts is None or parts.scheme != "https" or not parts.hostname:
            raise _fail(path, name, "'url' is an https:// address")
        if "@" in parts.netloc or parts.query or parts.fragment:
            raise _fail(path, name, "'url' carries no credentials, query or fragment")
    if command is not None and command not in REGISTRY:
        raise _fail(path, name, f"'command' is {' or '.join(sorted(REGISTRY))}, running a pin")
    _check_args(path, name, list(args or []))
    for value in (url or "", command or ""):
        _check_arg(path, name, value)
    env = raw.get("env", {})
    if not isinstance(env, dict):
        raise _fail(path, name, "'env' maps names to default values")
    for key, value in env.items():
        if not ENV_NAME.fullmatch(key) or not isinstance(value, str) or not _printable(value):
            raise _fail(path, name, f"env {key!r}: an upper-case name and a printable default")
        if key in MACHINE_ENV or GUID.search(value):
            raise _fail(path, name, f"env {key!r}: tenant, subscription and client IDs belong to "
                        f"each machine (az login or its environment), not the catalog")  # fmt: skip
        allowed = NOT_SECRET.get(key)
        if allowed is not None and value.casefold() not in allowed:
            raise _fail(path, name, f"env {key!r}: one of {sorted(allowed)}")
        secret_name = SECRET_NAME.search(key) and allowed is None
        if "$" in value or "}" in value or secret_name or SECRET_VALUE.match(value):
            raise _fail(path, name, f"env {key!r}: servers are keyless; no secrets or placeholders")
    if url is not None and env:
        raise _fail(path, name, "a url server has no 'env'")
    pin = _pin(path, name, raw.get("pin"))
    if command is not None:
        if pin is None:
            raise _fail(path, name, f"a {command} server needs a 'pin'")
        if pin.registry != REGISTRY[command]:
            raise _fail(path, name, f"a {command} server's pin is on {REGISTRY[command]}")
        if not runs_pin(command, args, pin):
            raise _fail(path, name, f"the {command} args must run the pinned package first")
    elif pin is not None:
        raise _fail(path, name, "a url server has no 'pin'")
    if any("azmcp" in arg for arg in args) and "--read-only" not in args:
        raise _fail(path, name, "an Azure MCP server runs --read-only")
    pack_flags = raw.get("packArgs", [])
    if not _strings(pack_flags) or not all(FLAG.fullmatch(flag) for flag in pack_flags):
        raise _fail(path, name, "'packArgs' lists the --flags a pack may add")
    for flag in pack_flags:
        _check_args(path, name, [flag])
        if flag in {"--read-only", "--transport", "--mode", "--tool"} or flag in args:
            raise _fail(path, name, f"'packArgs': {flag} decides what the server may do")
    deny = raw.get("deny", [])
    if not _strings(deny) or not all(TOOL_NAME.fullmatch(tool) for tool in deny):
        raise _fail(path, name, "'deny' lists tool names")
    for tool in deny:
        if len(f"mcp__{name}__{tool}") > MAX_TOOL_NAME:
            raise _fail(path, name, f"mcp__{name}__{tool} is longer than {MAX_TOOL_NAME}")
    codex = raw.get("codex", {})
    if not isinstance(codex, dict) or set(codex) - CODEX_KEYS:
        raise _fail(path, name, f"'codex' takes {sorted(CODEX_KEYS)}")
    timeouts = {}
    for key in ("startup_timeout_sec", "tool_timeout_sec"):
        value = codex.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float)):
            raise _fail(path, name, f"'codex.{key}' is a number of seconds")
        timeouts[key] = float(value) if value is not None else None
    enabled = codex.get("enabled_tools")
    if enabled is not None and not _strings(enabled):
        raise _fail(path, name, "'codex.enabled_tools' lists tool names")
    for key in ("source", "why"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise _fail(path, name, f"'{key}' says where it comes from and why it's here")
    return Server(
        name=name,
        scope=scope,
        clients=frozenset(clients),
        command=command,
        args=tuple(args),
        url=url,
        env=dict(env),
        pin=pin,
        deny=tuple(deny),
        startup_timeout_sec=timeouts["startup_timeout_sec"],
        tool_timeout_sec=timeouts["tool_timeout_sec"],
        enabled_tools=tuple(enabled) if enabled is not None else None,
        source=raw["source"],
        why=raw["why"],
        pack_flags=tuple(pack_flags),
    )


def load_mcp_servers(agents_dir: Path) -> dict[str, Server]:
    """Read <agents_dir>/mcp-servers.json; a catalog without one has no servers."""
    path = agents_dir / MCP_SERVERS_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != 1
        or not isinstance(raw.get("servers"), dict)
    ):
        raise ValueError(f'{path}: expected {{"schema": 1, "servers": {{...}}}}')
    return {name: _server(path, name, value) for name, value in raw["servers"].items()}


def pack_servers(
    agents_dir: Path, servers: Mapping[str, Server]
) -> dict[str, list[tuple[str, dict[str, tuple[str, ...]]]]]:
    """{pack: [(server, {flag: values})]} from the packs' "mcp" lists in skill-packs.json: a
    server name, or {"server": name, "args": {"--flag": [values]}}."""
    path = agents_dir / "skill-packs.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text())
    found: dict[str, list[tuple[str, dict[str, tuple[str, ...]]]]] = {}
    for pack, definition in raw.items() if isinstance(raw, dict) else []:
        if isinstance(definition, dict) and set(definition) - PACK_KEYS:
            unknown = sorted(set(definition) - PACK_KEYS)
            raise ValueError(f"{path}: pack {pack!r}: unknown keys {unknown}")
        refs = definition.get("mcp", []) if isinstance(definition, dict) else []
        for ref in refs if isinstance(refs, list) else [refs]:
            if isinstance(ref, dict) and set(ref) - REF_KEYS:
                raise ValueError(f"{path}: pack {pack!r}: an MCP ref takes {sorted(REF_KEYS)}")
            name: Any = (
                ref
                if isinstance(ref, str)
                else ref.get("server")
                if isinstance(ref, dict)
                else None
            )
            args: Any = ref.get("args", {}) if isinstance(ref, dict) else {}
            if not isinstance(name, str) or name not in servers:
                raise ValueError(
                    f"{path}: pack {pack!r} uses MCP server {name!r}, not in {MCP_SERVERS_NAME}"
                )
            if servers[name].scope != "pack":
                raise ValueError(f"{path}: pack {pack!r} uses {name!r}, a global server")
            if not isinstance(args, dict) or not all(
                isinstance(flag, str) and FLAG.fullmatch(flag) and _strings(values)
                for flag, values in args.items()
            ):
                raise ValueError(f"{path}: pack {pack!r}: 'args' maps --flags to lists of values")
            for flag, values in args.items():
                if flag not in servers[name].pack_flags:
                    allowed = list(servers[name].pack_flags) or "none"
                    raise ValueError(
                        f"{path}: pack {pack!r}: {name!r} takes {allowed} from packs ('packArgs'), "
                        f"not {flag}"
                    )
                _check_args(path, f"pack {pack!r}", [arg for v in values for arg in (flag, v)])
            found.setdefault(pack, []).append((name, {flag: tuple(v) for flag, v in args.items()}))
    return found


def for_packs(
    packs: Sequence[str],
    servers: Mapping[str, Server],
    refs: Mapping[str, list[tuple[str, dict[str, tuple[str, ...]]]]],
) -> dict[str, Server]:
    """The pack servers a repository with these packs runs, each with the union of the packs'
    extra args (sorted, so the result doesn't depend on pack order)."""
    union: dict[str, dict[str, set[str]]] = {}
    for pack in packs:
        for name, args in refs.get(pack, []):
            flags = union.setdefault(name, {})
            for flag, values in args.items():
                flags.setdefault(flag, set()).update(values)
    return {
        name: _with_pack_args(servers[name], {flag: tuple(sorted(v)) for flag, v in flags.items()})
        for name, flags in sorted(union.items())
    }


def _with_pack_args(server: Server, args: dict[str, tuple[str, ...]]) -> Server:
    from dataclasses import replace

    return replace(server, pack_args=dict(sorted(args.items())))


# Rendering.


def _args(server: Server, cache: str) -> list[str]:
    args = [arg.replace(CACHE, cache) for arg in server.args]
    for flag, values in server.pack_args.items():
        for value in values:
            args += [flag, value]
    if server.command == "uvx" and server.pin and "--exclude-newer" not in args:
        args[:0] = ["--exclude-newer", _cutoff(server.pin)]
    return args


def _cutoff(pin: Pin) -> str:
    """The end of the day the pin was published (UTC): what a cooldown lets in alongside it."""
    published = datetime.fromisoformat(pin.published_at.replace("Z", "+00:00")).astimezone(UTC)
    day = (published + timedelta(days=1)).date()
    return f"{day.isoformat()}T00:00:00Z"


def _env(server: Server, cache: str) -> dict[str, str]:
    env = dict(server.env)
    if server.command == "npx" and server.pin:
        env.setdefault("npm_config_before", _cutoff(server.pin))
        env.setdefault("npm_config_cache", f"{cache}/npm")
    return env


def claude_entry(server: Server, cache: str) -> dict[str, Any]:
    """A Claude Code mcpServers entry, in the normalized form `claude mcp add-json` stores.
    Each env default is a `${NAME:-default}`, so a machine can override it by exporting NAME;
    the npm cooldown settings repo-template adds are literal."""
    if server.url is not None:
        return {"type": "http", "url": server.url}
    entry: dict[str, Any] = {
        "type": "stdio",
        "command": server.command,
        "args": _args(server, cache),
    }
    env = {key: f"${{{key}:-{value}}}" for key, value in server.env.items()}
    env.update((key, value) for key, value in _env(server, cache).items() if key not in server.env)
    if env:
        entry["env"] = dict(sorted(env.items()))
    return entry


def codex_value(server: Server, cache: str) -> dict[str, Any]:
    """A Codex [mcp_servers.<name>] table, as tomllib parses what codex_toml() writes. Literal
    values: Codex expands no placeholders."""
    value: dict[str, Any] = {}
    if server.url is not None:
        value["url"] = server.url
    else:
        value["command"] = server.command
        value["args"] = _args(server, cache)
    for key in ("startup_timeout_sec", "tool_timeout_sec"):
        seconds = getattr(server, key)
        if seconds is not None:
            value[key] = seconds
    if server.enabled_tools is not None:
        value["enabled_tools"] = list(server.enabled_tools)
    if server.deny:
        value["disabled_tools"] = sorted(server.deny)
    env = _env(server, cache)
    if env:
        value["env"] = dict(sorted(env.items()))
    return value


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(float(value))
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # a TOML basic string
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise TypeError(f"no TOML for {value!r}")


def codex_toml(name: str, value: Mapping[str, Any]) -> str:
    """[mcp_servers.<name>] (and its env subtable) in the layout Codex itself writes, so a
    `codex mcp add` elsewhere in the file leaves it as it is."""
    lines = [f"[mcp_servers.{name}]"]
    lines += [f"{key} = {toml_value(item)}" for key, item in value.items() if key != "env"]
    if value.get("env"):
        lines += ["", f"[mcp_servers.{name}.env]"]
        lines += [f"{key} = {toml_value(item)}" for key, item in value["env"].items()]
    return "\n".join(lines) + "\n"


def digest(value: Any) -> str:
    """A hash of a parsed entry, with numbers as floats (Codex rewrites 30 as 30.0)."""

    def normal(item: Any) -> Any:
        if isinstance(item, bool) or item is None or isinstance(item, str):
            return item
        if isinstance(item, int | float):
            return float(item)
        if isinstance(item, list):
            return [normal(element) for element in item]
        if isinstance(item, dict):
            return {key: normal(element) for key, element in item.items()}
        return item

    text = json.dumps(normal(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def deny_rules(servers: Mapping[str, Server]) -> set[str]:
    """The Claude Code permission rules that keep every server's denied tools out: one glob per
    tool, so it also covers the tool under any server or plugin name."""
    return {f"mcp__*__{tool}" for server in servers.values() for tool in server.deny}
