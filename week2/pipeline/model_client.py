"""Unified LLM client module for multiple providers."""

from pathlib import Path

import httpx
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Any, TextIO

# Load environment variables from .env file if it exists
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger = logging.getLogger(__name__)
    logger.info(f"Loaded environment variables from {env_path}")
else:
    logger = logging.getLogger(__name__)
    logger.warning("No .env file found, using system environment variables")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "input_price": 0.14,  # per 1M tokens
        "output_price": 0.28,  # per 1M tokens
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
        "input_price": 0.0008,  # per 1K tokens
        "output_price": 0.002,  # per 1K tokens
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
        "input_price": 0.5,  # per 1M tokens
        "output_price": 1.5,  # per 1M tokens
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4",
        "input_price": 0.1,  # per 1M tokens (approximate)
        "output_price": 0.1,  # per 1M tokens (approximate)
    },
}


@dataclass
class Usage:
    """Token usage statistics."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """LLM response with content and usage."""

    content: str
    usage: Usage
    model: str
    provider: str


COST_TABLE: dict[str, dict[str, float]] = {
    "deepseek": {"input": 1.0, "output": 2.0},
    "qwen": {"input": 4.0, "output": 12.0},
    "openai": {"input": 150.0, "output": 600.0},
}


class CostTracker:
    """Track LLM API token usage and estimated cost in CNY.

    Prices are in yuan per million tokens. The tracker accumulates
    usage across multiple API calls and can produce a summary report
    broken down by provider.

    Attributes:
        records: Per-provider lists of (prompt_tokens, completion_tokens) tuples.
        total_calls: Total number of recorded API calls.
    """

    def __init__(self) -> None:
        self.records: dict[str, list[tuple[int, int]]] = {}
        self.total_calls: int = 0

    def record(self, usage: Usage, provider: str) -> None:
        """Record token usage from a single API call.

        Args:
            usage: Token usage statistics returned by the LLM.
            provider: Provider name (e.g. 'deepseek', 'qwen', 'openai').
        """
        self.records.setdefault(provider, []).append(
            (usage.prompt_tokens, usage.completion_tokens)
        )
        self.total_calls += 1

    def estimated_cost(self, provider: str) -> float:
        """Return the estimated cost in CNY for a specific provider.

        Args:
            provider: Provider name to calculate cost for.

        Returns:
            Estimated cost in yuan. Returns 0.0 if provider has no records.

        Raises:
            ValueError: If the provider is not in COST_TABLE.
        """
        if provider not in COST_TABLE:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported: {list(COST_TABLE.keys())}"
            )

        prices = COST_TABLE[provider]
        total_input = sum(r[0] for r in self.records.get(provider, []))
        total_output = sum(r[1] for r in self.records.get(provider, []))

        input_cost = (total_input / 1_000_000) * prices["input"]
        output_cost = (total_output / 1_000_000) * prices["output"]

        return input_cost + output_cost

    def report(self, provider: str | None = None, file: TextIO | None = None) -> None:
        """Print a cost report to the given output stream.

        When *provider* is specified only that provider's report is printed;
        otherwise every provider with recorded usage is included.

        Args:
            provider: Optional provider name to filter the report.
            file: Output stream (defaults to sys.stdout).
        """
        import sys

        out = file or sys.stdout
        providers = [provider] if provider else list(self.records.keys())
        grand_total = 0.0

        print("=" * 60, file=out)
        print("LLM Cost Report (CNY)", file=out)
        print("=" * 60, file=out)

        for name in providers:
            entries = self.records.get(name, [])
            if not entries:
                continue

            total_input = sum(r[0] for r in entries)
            total_output = sum(r[1] for r in entries)
            calls = len(entries)
            cost = self.estimated_cost(name)
            grand_total += cost

            print(f"\n  Provider : {name}", file=out)
            print(f"  Calls    : {calls}", file=out)
            print(f"  Input    : {total_input:>10,} tokens", file=out)
            print(f"  Output   : {total_output:>10,} tokens", file=out)
            print(f"  Cost     : ¥{cost:.6f}", file=out)

        print(f"\n  Total    : ¥{grand_total:.6f} ({self.total_calls} calls)", file=out)
        print("=" * 60, file=out)


tracker = CostTracker()


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send chat request to LLM provider.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            model: Model name to use.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMResponse containing the response content and usage stats.

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        pass

    @abstractmethod
    def get_api_key(self) -> str:
        """Get API key for the provider.

        Returns:
            API key string.

        Raises:
            ValueError: If API key is not configured.
        """
        pass


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible API provider implementation."""

    def __init__(self, base_url: str, api_key_env_var: str, model: str):
        """Initialize the provider.

        Args:
            base_url: Base URL for the API.
            api_key_env_var: Environment variable name for API key.
            model: Default model name.
        """
        self.base_url = base_url
        self.api_key_env_var = api_key_env_var
        self.default_model = model
        self.timeout = httpx.Timeout(60.0)

    def get_api_key(self) -> str:
        """Get API key from environment variable.

        The API key is read from the environment variable specified in
        api_key_env_var. Environment variables can be set in .env file.

        Returns:
            API key string.

        Raises:
            ValueError: If API key is not configured.
        """
        api_key = os.getenv(self.api_key_env_var)
        if not api_key:
            raise ValueError(f"API key not found in environment variable: {self.api_key_env_var}")
        return api_key

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send chat request to OpenAI-compatible API.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            model: Model name to use (uses default if None).
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMResponse containing the response content and usage stats.

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        model_to_use = model or self.default_model

        headers = {
            "Authorization": f"Bearer {self.get_api_key()}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        logger.info(f"Sending request to {model_to_use} with {len(messages)} messages")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage_data = data.get("usage", {})

        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(
            content=content,
            usage=usage,
            model=model_to_use,
            provider=self.api_key_env_var.replace("_API_KEY", ""),
        )


def get_provider() -> OpenAICompatibleProvider:
    """Get configured LLM provider based on environment variable.

    The provider is selected using the LLM_PROVIDER environment variable
    (default: 'deepseek'). API keys are read from environment variables:
    - DEEPSEEK_API_KEY for DeepSeek
    - QWEN_API_KEY for Qwen
    - OPENAI_API_KEY for OpenAI

    Environment variables can be set in .env file in the project root.

    Returns:
        OpenAICompatibleProvider instance.

    Raises:
        ValueError: If provider is not supported or not configured.
    """
    provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider_name not in PROVIDER_CONFIG:
        raise ValueError(f"Unsupported provider: {provider_name}. Supported: {list(PROVIDER_CONFIG.keys())}")

    config = PROVIDER_CONFIG[provider_name]

    api_key_env = f"{provider_name.upper()}_API_KEY"

    provider = OpenAICompatibleProvider(
        base_url=config["base_url"],
        api_key_env_var=api_key_env,
        model=config["model"],
    )

    logger.info(f"Initialized {provider_name} provider with model {config['model']}")
    return provider


async def chat_with_retry(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    max_retries: int = 3,
) -> LLMResponse:
    """Send chat request with retry logic.

    Args:
        messages: List of message dictionaries with 'role' and 'content'.
        model: Model name to use.
        temperature: Sampling temperature (0.0 to 2.0).
        max_tokens: Maximum tokens to generate.
        max_retries: Maximum number of retry attempts.

    Returns:
        LLMResponse containing the response content and usage stats.

    Raises:
        httpx.HTTPError: If all retry attempts fail.
    """
    provider = get_provider()
    provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()

    for attempt in range(max_retries):
        try:
            response = await provider.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            tracker.record(response.usage, provider_name)
            return response
        except httpx.HTTPError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"All {max_retries} attempts failed")
                raise


def estimate_tokens(text: str) -> int:
    """Estimate number of tokens in text.

    Rough estimation: ~4 characters per token for English text.

    Args:
        text: Input text to estimate.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


def calculate_cost(response: LLMResponse, provider_name: str | None = None) -> float:
    """Calculate cost in USD for API usage.

    Args:
        response: LLMResponse from API call.
        provider_name: Provider name (uses LLM_PROVIDER env var if None).

    Returns:
        Cost in USD.
    """
    provider_name = provider_name or os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider_name not in PROVIDER_CONFIG:
        raise ValueError(f"Unknown provider: {provider_name}")

    config = PROVIDER_CONFIG[provider_name]

    input_price = config["input_price"]
    output_price = config["output_price"]

    input_cost = (response.usage.prompt_tokens / 1_000_000) * input_price
    output_cost = (response.usage.completion_tokens / 1_000_000) * output_price

    return input_cost + output_cost


async def quick_chat(
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """Convenient function for quick chat with LLM.

    Args:
        prompt: User prompt text.
        system_prompt: System message to set context.
        temperature: Sampling temperature (0.0 to 2.0).
        max_tokens: Maximum tokens to generate.

    Returns:
        Response content string.

    Raises:
        httpx.HTTPError: If the API request fails.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    response = await chat_with_retry(messages, temperature=temperature, max_tokens=max_tokens)
    return response.content


async def main() -> None:
    """Test the LLM client functionality."""
    logger.info("Starting LLM client test")

    try:
        provider = get_provider()
        logger.info(f"Provider initialized: {provider}")

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Can you help me?"},
        ]

        response = await chat_with_retry(messages)
        logger.info(f"Response: {response.content[:100]}...")
        logger.info(f"Usage: {response.usage}")

        cost = calculate_cost(response)
        logger.info(f"Estimated cost: ${cost:.6f}")

        quick_response = await quick_chat("What is Python?")
        logger.info(f"Quick chat response: {quick_response[:100]}...")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
    except httpx.HTTPError as e:
        logger.error(f"API error: {e}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
