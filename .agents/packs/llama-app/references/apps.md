# What the Llama app launches, per platform

Checked 2026-11-18 against Llama-macOS 0.48.0 (`Llama/Server/LlamaServer.swift`,
`buildLaunchSpec`; `Llama/Server/UserModelOverrides.swift`; `readme.md`) and Llama-Windows
`main` (`LlamaApp.LlamaCpp/LlamaManager.cs`, `BuildServeArguments`; `Settings.cs`;
`LlamaApp.Common/ServerAuth.cs`; `README.md`), plus `https://llama.app/install.sh`.

| | macOS app | Windows app | Linux (CLI only) |
| --- | --- | --- | --- |
| Install | `brew install --cask llama-app`, or the download on Releases | `.msixbundle` from Releases; `irm https://llama.app/install.ps1 \| iex` installs only the CLI | `curl -LsSf https://llama.app/install.sh \| sh` puts `llama` in `~/.local/bin` (the latest pointer was `b12375`; `LLAMA_VERSION=b12375` pins it) |
| Command | `llama serve --models-preset "~/Library/Application Support/Llama/models.ini" --log-file ... --port 9931 --models-max 0 --models-memory-margin <MiB> --fit-target <MiB> --sleep-idle-seconds 300 --spec-default`, plus `--host` when network access is on and `--agent` in agent mode | `llama serve --host 127.0.0.1 --port 9931 --jinja --models-dir %USERPROFILE%\.llama\models --sleep-idle-seconds 300 --models-max 1 --models-preset %USERPROFILE%\.llama\model-context-presets.ini`, plus `--cache-type-k/-v` when set | `llama serve` (router) or `llama serve -hf org/repo:QUANT` |
| Model cache | `~/.cache/huggingface/hub`, passed to the server as `HF_HUB_CACHE` (`LLAMA_CACHE` is set to an empty path) | `%USERPROFILE%\.cache\huggingface\hub`, passed as `HF_HUB_CACHE` | first set of `LLAMA_CACHE`, `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE`, `$HF_HOME/hub`, `$XDG_CACHE_HOME/huggingface/hub`, else `~/.cache/huggingface/hub` |
| Your settings | `~/.config/llama/models.user.ini` (a commented template is written on first launch); `defaults write app.llama.Llama extraServerArgs -string "..."` appends flags | the Settings window: idle unload (300 s default, -1 off), max loaded models (1 default, 0 unlimited), KV cache types, custom serve arguments, and Settings > General > Model folders for GGUFs kept elsewhere; `settings.json` and logs under `%LOCALAPPDATA%\Llama` | flags, `LLAMA_ARG_*` variables, or `~/.config/llama.cpp/config.ini` (only its `[*]` section is read) |
| Idle unload | Settings: 5m (default), 15m, 1h, Off | `IdleUnloadSeconds` in the app settings (300 default, -1 off) | `--sleep-idle-seconds N` |
| Network | Settings > Allow network access: Tailscale (authenticated and encrypted; shown when Tailscale is installed and signed in) or This network (`0.0.0.0`, no password). `defaults write app.llama.Llama exposeToNetwork -string "<ip>"` pins one address; the app falls back to localhost when that address is on no interface | Settings > Llama: loopback (default), `0.0.0.0`, or one interface. Any non-loopback bind makes the app generate a key, pass it as `LLAMA_API_KEY`, and send it as a Bearer token; the lock glyph in the flyout footer copies it, and a checkbox requires it on loopback too | `--host`, `--api-key` |

## Overriding what the macOS app generates

The app regenerates `models.ini` from a scan of the cache on every launch and merges
`models.user.ini` into it:

- Use the app's section header (`org/repo:QUANT`) and list only the keys you change. Keys are
  `llama serve` options without the leading dashes (`temp`, `ctx-size`, `cache-type-k`).
- A section for a model the app did not find is passed through as is: that is how you point at
  a local GGUF (`model = /path/to/file.gguf`) or a draft model from another repo.
- Anything there wins over the app's own value, including settings derived from the Mac's
  memory. A key the server rejects makes the app ignore the whole file and name the key in its
  menu.
- `extraServerArgs` go after the app's own flags, so where the server honors the later
  occurrence (for example `--api-key`) they override it. They take effect on the next server
  start.

## Overriding what the Windows app generates

The preset INI is app-owned and rewritten from the per-model context picker and detected draft
heads; the `--models-dir` is reserved for "Open With > Llama". Custom serve arguments are
appended last, so they override the app's flags, except the bind and API-key flags (`--host`,
`--api-key`, `--api-key-file`), which the app refuses. Everything the server reads from disk
lives under `%USERPROFILE%\.llama` because MSIX virtualizes `%LOCALAPPDATA%` writes away from
the out-of-package `llama.exe`.
