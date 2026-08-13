"""Model providers.

Two ways to reach a model, same interface:

- ClaudeCLI  — shells out to the `claude` CLI (Claude Code). Zero dependencies,
               works on a Claude subscription with no API key.
- AnthropicAPI — uses the `anthropic` Python SDK if installed and
               ANTHROPIC_API_KEY is set.

`get_provider()` picks the API if available, otherwise the CLI. Both take a
prompt string and return the model's text response.
"""

import os
import shutil
import subprocess


class ProviderError(RuntimeError):
    pass


class ClaudeCLI:
    name = "claude-cli"

    def __init__(self):
        if shutil.which("claude") is None:
            raise ProviderError("`claude` CLI not found on PATH")

    def complete(self, prompt: str, model: str, timeout: int = 180) -> str:
        result = subprocess.run(
            ["claude", "-p", "--model", model, "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise ProviderError(
                f"claude CLI exited {result.returncode}: {result.stderr.strip()[:500]}"
            )
        return result.stdout.strip()


class AnthropicAPI:
    name = "anthropic-api"

    # CLI aliases -> API model IDs. Adjust to taste.
    MODEL_MAP = {
        "sonnet": "claude-sonnet-5",
        "haiku": "claude-haiku-4-5-20251001",
    }

    def __init__(self):
        import anthropic  # raises ImportError if not installed

        self.client = anthropic.Anthropic()  # needs ANTHROPIC_API_KEY

    def complete(self, prompt: str, model: str, timeout: int = 180) -> str:
        response = self.client.messages.create(
            model=self.MODEL_MAP.get(model, model),
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()


def get_provider():
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicAPI()
        except ImportError:
            pass
    return ClaudeCLI()
