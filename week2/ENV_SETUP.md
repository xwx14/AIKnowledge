# Environment Configuration Guide

## Setup

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

  2. Edit `.env` and fill in your actual API keys:
    ```bash
    # Select provider: deepseek, qwen, openai, or glm
    LLM_PROVIDER=deepseek

    # Fill in your API keys
    DEEPSEEK_API_KEY=your_deepseek_api_key_here
    QWEN_API_KEY=your_qwen_api_key_here
    OPENAI_API_KEY=your_openai_api_key_here
    GLM_API_KEY=your_glm_api_key_here
    ```

## Getting API Keys

### DeepSeek
1. Visit https://platform.deepseek.com/api_keys
2. Sign up or log in
3. Create a new API key

### Qwen
1. Visit https://dashscope.console.aliyun.com/apiKey
2. Sign up or log in with Alibaba Cloud
3. Create a new API key

### OpenAI
1. Visit https://platform.openai.com/api-keys
2. Sign up or log in
3. Create a new API key

### GLM (智谱AI)
1. Visit https://open.bigmodel.cn/usercenter/apikeys
2. Sign up or log in with BigModel.cn
3. Create a new API key

## Usage

The LLM client will automatically read configuration from `.env` file:

```python
from pipeline.model_client import get_provider, quick_chat

# Provider is automatically selected based on LLM_PROVIDER in .env
provider = get_provider()

# Quick chat
response = await quick_chat("Hello!")
```

## Security

- `.env` is included in `.gitignore` to prevent accidental commits
- Never commit your `.env` file to version control
- Keep your API keys secure
- Rotate API keys regularly

## Switching Providers

Simply change the `LLM_PROVIDER` variable in `.env`:

```bash
# Switch to Qwen
LLM_PROVIDER=qwen
QWEN_API_KEY=your_qwen_api_key_here
```

The client will automatically use the new provider on next run.
