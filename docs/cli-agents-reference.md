# CLI Agents Reference: Codex & Gemini CLI

Headless execution reference for OpenAI Codex CLI and Google Gemini CLI.

---

## OpenAI Codex CLI

### Headless Execution: `codex exec`

The `exec` subcommand (alias: `codex e`) runs non-interactively.

```bash
codex exec "your prompt here"
```

### Global Flags

| Flag        | Alias | Values      | Description                                         |
| ----------- | ----- | ----------- | --------------------------------------------------- |
| `--model`   | `-m`  | string      | Override model (default: `gpt-5-codex`)             |
| `--profile` | `-p`  | string      | Load profile from `~/.codex/config.toml`            |
| `--config`  | `-c`  | key=value   | Override config values (parsed as JSON if possible) |
| `--cd`      | `-C`  | path        | Set working directory before starting               |
| `--image`   | `-i`  | path[,path] | Attach image files to prompt                        |
| `--search`  | —     | boolean     | Enable web search tool                              |
| `--oss`     | —     | boolean     | Use local Ollama model provider                     |

### Approval & Sandbox Flags

| Flag                                         | Alias    | Description                                             |
| -------------------------------------------- | -------- | ------------------------------------------------------- |
| `--suggest`                                  | —        | Show changes, require explicit approval                 |
| `--auto-edit`                                | —        | Auto-edit files in workspace, ask for external commands |
| `--full-auto`                                | —        | Full workspace access, network enabled                  |
| `--sandbox`                                  | `-s`     | `read-only` / `workspace-write` / `danger-full-access`  |
| `--ask-for-approval`                         | `-a`     | `untrusted` / `on-failure` / `on-request` / `never`     |
| `--dangerously-bypass-approvals-and-sandbox` | `--yolo` | No approvals, no sandbox (dangerous)                    |
| `--add-dir`                                  | —        | Grant additional directories write access               |

### Output Flags (exec-specific)

| Flag                    | Description                                         |
| ----------------------- | --------------------------------------------------- |
| `--json`                | Output in JSON format                               |
| `--color`               | Force colored output                                |
| `--output-last-message` | Write final agent message to file                   |
| `--output-schema`       | JSON Schema file to constrain final response format |
| `--skip-git-repo-check` | Skip git repository validation                      |

### Examples

```bash
# Simple headless execution
codex exec "fix the failing test in src/utils.ts"

# Full auto mode for trusted tasks
codex exec --full-auto "update CHANGELOG for v2.0 release"

# CI/CD with JSON output
codex exec --json --full-auto "review this PR" > review.json

# Attach screenshot for context
codex exec -i screenshot.png "implement this design"

# Use specific model
codex exec -m gpt-5 "refactor this function"

# YOLO mode (no approvals, dangerous)
codex exec --yolo "run all tests and fix failures"
```

### Environment Variables

| Variable            | Purpose                               |
| ------------------- | ------------------------------------- |
| `OPENAI_API_KEY`    | API authentication                    |
| `EDITOR` / `VISUAL` | Editor for Ctrl+G in interactive mode |

### Configuration

Config file: `~/.codex/config.toml`

```toml
[default]
model = "gpt-5-codex"
approval_mode = "auto-edit"

[profiles.ci]
model = "gpt-5"
approval_mode = "full-auto"
```

---

## Google Gemini CLI

### Headless Execution

Use `-p` or `--prompt` flag for non-interactive mode:

```bash
gemini -p "your prompt here"
```

### Command Line Flags

| Flag                    | Alias | Description                                                |
| ----------------------- | ----- | ---------------------------------------------------------- |
| `--prompt`              | `-p`  | Run in headless mode with prompt                           |
| `--model`               | `-m`  | Specify model (e.g., `gemini-2.5-flash`, `gemini-2.5-pro`) |
| `--output-format`       | —     | `text` (default), `json`, `stream-json`                    |
| `--yolo`                | `-y`  | Auto-approve all actions (no confirmations)                |
| `--approval-mode`       | —     | Set approval mode (e.g., `auto_edit`)                      |
| `--all-files`           | `-a`  | Include all files in context                               |
| `--include-directories` | —     | Add directories to context (comma-separated)               |
| `--debug`               | `-d`  | Enable debug output                                        |

### Output Formats

```bash
# Plain text (default)
gemini -p "explain this code"

# JSON (structured, includes metadata)
gemini -p "explain this code" --output-format json

# Streaming JSON (JSONL, real-time)
gemini -p "explain this code" --output-format stream-json
```

### Examples

```bash
# Simple headless query
gemini -p "what does this function do?"

# With specific model
gemini -p "optimize this code" -m gemini-2.5-pro

# Include additional directories
gemini -p "review the codebase" --include-directories ../lib,../docs

# JSON output for scripting
gemini -p "list all API endpoints" --output-format json > endpoints.json

# YOLO mode (auto-approve all actions)
gemini -p "fix all linting errors" --yolo

# Pipe input
cat error.log | gemini -p "what went wrong?"
echo "def foo(): pass" | gemini -p "add type hints"

# File redirection
gemini -p "summarize this log" < big_log.txt
```

### Environment Variables

| Variable                    | Purpose                           |
| --------------------------- | --------------------------------- |
| `GEMINI_API_KEY`            | API authentication                |
| `GOOGLE_API_KEY`            | Alternative API key               |
| `GOOGLE_GENAI_USE_VERTEXAI` | Enable Vertex AI backend          |
| `GOOGLE_CLOUD_PROJECT`      | Project ID for Code Assist        |
| `GEMINI_SYSTEM_MD`          | Path to custom system prompt file |

### Configuration

Config file: `~/.gemini/settings.json`

```json
{
  "model": "gemini-2.5-pro",
  "mcpServers": {}
}
```

---

## Quick Comparison

| Feature        | Codex CLI          | Gemini CLI             |
| -------------- | ------------------ | ---------------------- |
| Headless flag  | `codex exec "..."` | `gemini -p "..."`      |
| YOLO mode      | `--yolo`           | `--yolo` or `-y`       |
| Model override | `-m` or `--model`  | `-m` or `--model`      |
| JSON output    | `--json`           | `--output-format json` |
| Image input    | `-i` or `--image`  | Not documented         |
| Stdin piping   | Limited            | Full support           |
| Auth env var   | `OPENAI_API_KEY`   | `GEMINI_API_KEY`       |

---

## Sources

- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)
- [Codex CLI Features](https://developers.openai.com/codex/cli/features/)
- [Codex GitHub](https://github.com/openai/codex)
- [Gemini CLI Headless Mode](https://google-gemini.github.io/gemini-cli/docs/cli/headless.html)
- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)
- [Gemini CLI Documentation](https://geminicli.com/docs/)
