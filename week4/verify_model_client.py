"""Final verification script for pipeline.model_client module."""

import os
import sys


def verify_imports():
    """Verify all imports work correctly."""
    print("Verifying imports...")
    try:
        from pipeline import model_client
        assert hasattr(model_client, "LLMProvider")
        assert hasattr(model_client, "LLMResponse")
        assert hasattr(model_client, "Usage")
        assert hasattr(model_client, "OpenAICompatibleProvider")
        assert hasattr(model_client, "get_provider")
        assert hasattr(model_client, "chat_with_retry")
        assert hasattr(model_client, "quick_chat")
        assert hasattr(model_client, "estimate_tokens")
        assert hasattr(model_client, "calculate_cost")
        print("[OK] All imports successful")
        return True
    except ImportError as e:
        print(f"[FAIL] Import error: {e}")
        return False


def verify_provider_config():
    """Verify provider configuration."""
    print("\nVerifying provider configuration...")
    from pipeline.model_client import PROVIDER_CONFIG

    required_providers = ["deepseek", "qwen", "glm", "kimi"]
    for provider in required_providers:
        assert provider in PROVIDER_CONFIG, f"Missing provider: {provider}"
        config = PROVIDER_CONFIG[provider]
        assert "base_url" in config
        assert "model" in config
        assert "input_price" in config
        assert "output_price" in config

    print("[OK] All providers configured correctly")
    return True


def verify_dataclasses():
    """Verify dataclass definitions."""
    print("\nVerifying dataclass definitions...")
    from pipeline.model_client import LLMResponse, Usage

    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5
    assert usage.total_tokens == 15

    response = LLMResponse(
        content="Test", usage=usage, model="test-model", provider="test"
    )
    assert response.content == "Test"
    assert response.usage.total_tokens == 15

    print("[OK] Dataclass definitions work correctly")
    return True


def verify_utility_functions():
    """Verify utility functions."""
    print("\nVerifying utility functions...")
    from pipeline.model_client import estimate_tokens, calculate_cost, get_provider

    token_estimate = estimate_tokens("Hello world")
    assert isinstance(token_estimate, int)
    assert token_estimate > 0

    os.environ["LLM_PROVIDER"] = "deepseek"
    provider = get_provider()
    assert provider.api_key_env_var == "DEEPSEEK_API_KEY"

    print("[OK] Utility functions work correctly")
    return True


def verify_error_handling():
    """Verify error handling."""
    print("\nVerifying error handling...")
    from pipeline.model_client import get_provider

    os.environ["LLM_PROVIDER"] = "invalid"
    try:
        provider = get_provider()
        print("[FAIL] Should have raised ValueError")
        return False
    except ValueError:
        pass

    os.environ["LLM_PROVIDER"] = "deepseek"
    print("[OK] Error handling works correctly")
    return True


def verify_code_style():
    """Verify code style compliance."""
    print("\nVerifying code style...")
    try:
        import py_compile

        py_compile.compile("pipeline/model_client.py", doraise=True)
        print("[OK] Code style compliant")
        return True
    except py_compile.PyCompileError as e:
        print(f"[FAIL] Compilation error: {e}")
        return False


def main():
    """Run all verification tests."""
    print("=" * 70)
    print("Final Verification for pipeline.model_client")
    print("=" * 70)

    tests = [
        verify_imports,
        verify_provider_config,
        verify_dataclasses,
        verify_utility_functions,
        verify_error_handling,
        verify_code_style,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"[FAIL] Test failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 70)
    if all(results):
        print("All verification tests PASSED!")
        print("=" * 70)
        return 0
    else:
        print(f"Some tests FAILED: {sum(results)}/{len(results)} passed")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
