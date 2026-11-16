"""A self-hosted Stagehand MCP server.

Stagehand v4's act, extract and observe, with navigation, snapshots and screenshots, on a
headless local Chrome (a fresh profile each session) or a Chrome you host and reach over CDP,
answered by your own OpenAI-compatible model. There is no Browserbase code path: no API key,
cloud session, Model Gateway, server-side cache, fetch or search. A Chrome this server launches
can't resolve browserbase.com either.

Configuration is the environment:
  STAGEHAND_MODEL_BASE_URL  the model's OpenAI-compatible base URL, e.g. http://127.0.0.1:8000/v1
  STAGEHAND_MODEL           the model name that endpoint serves
  STAGEHAND_MODEL_API_KEY   optional, sent as a bearer token (set on the machine, never committed)
  STAGEHAND_MODEL_TIMEOUT   optional seconds per model call (120)
  STAGEHAND_CDP_URL         optional: attach to this Chrome instead of launching one
  STAGEHAND_CHROME_PATH     optional: the Chrome to launch
  STAGEHAND_HEADED          optional: 1 shows the launched browser
  STAGEHAND_ALLOWED_DOMAINS, STAGEHAND_BLOCKED_DOMAINS  optional comma-separated domain policy
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import sys
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from pydantic import Field, RootModel
from stagehand import Page, Stagehand, StagehandBrowser, local_browser

from stagehand_mcp.llm import Endpoint, generator

NO_BROWSERBASE = (
    "--host-resolver-rules=MAP browserbase.com ~NOTFOUND,MAP *.browserbase.com ~NOTFOUND"
)
NO_MODEL = (
    "no model is configured: set STAGEHAND_MODEL_BASE_URL (an OpenAI-compatible endpoint you "
    "host, ending in /v1) and STAGEHAND_MODEL on this machine, then restart the MCP server"
)
TRUE = {"1", "true", "yes", "on"}


def _domains(value: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    endpoint: Endpoint | None = None
    cdp_url: str | None = None
    chrome_path: str | None = None
    headed: bool = False
    allowed_domains: tuple[str, ...] = ()
    blocked_domains: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        base = env.get("STAGEHAND_MODEL_BASE_URL", "").strip()
        model = env.get("STAGEHAND_MODEL", "").strip()
        timeout = env.get("STAGEHAND_MODEL_TIMEOUT", "").strip()
        endpoint = None
        if base and model:
            endpoint = Endpoint(
                base_url=base,
                model=model,
                api_key=env.get("STAGEHAND_MODEL_API_KEY") or None,
                timeout=float(timeout) if timeout else 120.0,
            )
        return cls(
            endpoint=endpoint,
            cdp_url=env.get("STAGEHAND_CDP_URL", "").strip() or None,
            chrome_path=env.get("STAGEHAND_CHROME_PATH", "").strip() or None,
            headed=env.get("STAGEHAND_HEADED", "").strip().casefold() in TRUE,
            allowed_domains=_domains(env.get("STAGEHAND_ALLOWED_DOMAINS")),
            blocked_domains=_domains(env.get("STAGEHAND_BLOCKED_DOMAINS")),
        )


def _log(entry: Any) -> None:
    print(entry, file=sys.stderr)  # stdout carries the MCP protocol


class Session:
    """One browser and its Stagehand, started on the first tool call and replaced if the
    browser goes away."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient()
        self._browser: StagehandBrowser | None = None
        self._stagehand: Stagehand | None = None

    async def _open_browser(self) -> StagehandBrowser:
        if self.settings.cdp_url:
            return await local_browser.connect(cdp_url=self.settings.cdp_url)
        return await local_browser.launch(
            headless=not self.settings.headed,
            executable_path=self.settings.chrome_path,
            args=[NO_BROWSERBASE],
        )

    async def start(self) -> tuple[Stagehand, Page]:
        async with self._lock:
            browser = self._browser
            if self._stagehand is None or browser is None or browser.closed:
                await self._close()
                browser = await self._open_browser()
                try:
                    endpoint = self.settings.endpoint
                    self._stagehand = await Stagehand.create(
                        browser=browser,
                        model=generator(endpoint, self._client) if endpoint else None,
                        logging={"level": "warn", "on_log": _log},
                    )
                    if self.settings.allowed_domains or self.settings.blocked_domains:
                        policy: dict[str, Any] = {}
                        if self.settings.allowed_domains:
                            policy["allowed_domains"] = list(self.settings.allowed_domains)
                        if self.settings.blocked_domains:
                            policy["blocked_domains"] = list(self.settings.blocked_domains)
                        await browser.context.set_domain_policy(policy)  # type: ignore[arg-type]
                except BaseException:
                    await _quietly(browser.close())
                    raise
                self._browser = browser
            assert self._stagehand is not None
            context = browser.context
            page = await context.active_page() or next(iter(await context.pages()), None)
            return self._stagehand, page or await context.new_page()

    async def _close(self) -> None:
        stagehand, browser = self._stagehand, self._browser
        self._stagehand = self._browser = None
        if stagehand is not None:
            await _quietly(stagehand.close())
        if browser is not None and not browser.closed:
            await _quietly(browser.close())

    async def close(self) -> None:
        async with self._lock:
            await self._close()

    async def aclose(self) -> None:
        await self.close()
        await self._client.aclose()


async def _quietly(awaitable: Any) -> None:
    try:
        await awaitable
    except Exception as error:  # cleanup never hides the error that led to it
        _log(f"stagehand-mcp: cleanup failed: {error}")


def _schema_model(schema: dict[str, Any]) -> type[RootModel[Any]]:
    """A result type for extract that carries a caller's JSON schema as it is."""

    class Extracted(RootModel[Any]):
        @classmethod
        def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return schema

    return Extracted


def _require_model(session: Session) -> None:
    if session.settings.endpoint is None:
        raise ToolError(NO_MODEL)


def _actions(actions: Any) -> list[dict[str, Any]]:
    return [action.model_dump(mode="json", exclude_none=True) for action in actions]


INSTRUCTIONS = """\
Stagehand browser automation on a self-hosted browser and model. Navigate first, then use act
for one action described in plain language ("click the Sign in button"), observe to list the
actions a page offers (pass one back to act to replay it without another model call), and
extract to pull data out, optionally to a JSON schema. snapshot and screenshot show the page.
Keep secrets out of instructions: pass them in act's variables and refer to them as %name%.
"""


def build(settings: Settings) -> FastMCP:
    session = Session(settings)

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            await session.aclose()

    mcp = FastMCP(
        "stagehand",
        instructions=INSTRUCTIONS,
        version=importlib.metadata.version("stagehand-mcp"),
        lifespan=lifespan,
    )

    @mcp.tool(annotations={"title": "Go to a URL", "openWorldHint": True})
    async def navigate(url: Annotated[str, Field(description="The address to open")]) -> dict:
        """Open a URL in the browser, starting the browser if needed."""
        _, page = await session.start()
        await page.goto(url, wait_until="domcontentloaded")
        return {"url": await page.url(), "title": await page.title()}

    @mcp.tool(annotations={"title": "Act", "openWorldHint": True})
    async def act(
        instruction: Annotated[
            str | dict[str, Any],
            Field(description="One action in plain language, or an action observe returned"),
        ],
        variables: Annotated[
            dict[str, str] | None,
            Field(description="Values for %name% placeholders; never sent to the model"),
        ] = None,
    ) -> dict:
        """Perform one action on the current page: plain language, or an action observe
        returned, which replays with no model call."""
        _require_model(session)  # Stagehand wants one even to replay an observed action
        stagehand, page = await session.start()
        result = await stagehand.act(instruction, page=page, variables=variables)  # type: ignore[arg-type]
        data = result.data
        return {
            "success": data.success,
            "message": data.message,
            "description": data.action_description,
            "actions": _actions(data.actions or []),
        }

    @mcp.tool(annotations={"title": "Observe", "readOnlyHint": True, "openWorldHint": True})
    async def observe(
        instruction: Annotated[
            str | None, Field(description="What to look for, such as 'the search box'")
        ] = None,
    ) -> list[dict]:
        """List the actions the current page offers, each one ready to pass to act."""
        _require_model(session)
        stagehand, page = await session.start()
        result = await stagehand.observe(instruction, page=page)
        return _actions(result.data)

    @mcp.tool(annotations={"title": "Extract", "readOnlyHint": True, "openWorldHint": True})
    async def extract(
        instruction: Annotated[str, Field(description="What to extract from the page")],
        schema: Annotated[
            dict[str, Any] | None,
            Field(description="Optional JSON schema (an object) for the result"),
        ] = None,
    ) -> Any:
        """Extract data from the current page, as text or to a JSON schema."""
        _require_model(session)
        stagehand, page = await session.start()
        if schema is None:
            return (await stagehand.extract(instruction, page=page)).data.extraction
        result = await stagehand.extract(instruction, _schema_model(schema), page=page)
        return result.data.root

    @mcp.tool(annotations={"title": "Accessibility snapshot", "readOnlyHint": True})
    async def snapshot() -> str:
        """The current page's accessibility tree, as text."""
        _, page = await session.start()
        return (await page.snapshot()).formatted_tree

    @mcp.tool(annotations={"title": "Screenshot", "readOnlyHint": True})
    async def screenshot(
        full_page: Annotated[bool, Field(description="The whole page, not just the view")] = False,
    ) -> Image:
        """A PNG screenshot of the current page."""
        _, page = await session.start()
        return Image(data=await page.screenshot(full_page=full_page, type="png"), format="png")

    @mcp.tool(annotations={"title": "Close the browser", "idempotentHint": True})
    async def close() -> str:
        """Close the browser; the next tool call starts a fresh one."""
        await session.close()
        return "closed"

    return mcp


def main() -> None:
    build(Settings.from_env(os.environ)).run(show_banner=False)


if __name__ == "__main__":
    main()
