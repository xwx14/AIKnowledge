# GLM Provider Integration

## Summary

GLM (智谱AI) provider has been successfully integrated into the LLM client module.

## Configuration Details

- **Provider Name**: `glm`
- **Base URL**: `https://open.bigmodel.cn/api/paas/v4`
- **Default Model**: `glm-4`
- **Input Price**: $0.1 per 1M tokens
- **Output Price**: $0.1 per 1M tokens

## Usage

### 1. Set up .env file

```bash
# Select GLM as provider
LLM_PROVIDER=glm

# Add your GLM API key
GLM_API_KEY=your_actual_glm_api_key_here
```

### 2. Get API Key

Visit https://open.bigmodel.cn/usercenter/apikeys to obtain your GLM API key.

### 3. Use in Code

```python
from pipeline.model_client import get_provider, quick_chat
import asyncio

# Provider is automatically loaded from .env
provider = get_provider()

# Quick chat
response = await quick_chat("Hello, GLM!")
print(response)
```

## Supported Providers

The LLM client now supports 4 providers:

1. **deepseek** - DeepSeek Chat
2. **qwen** - Qwen Turbo (Alibaba Cloud)
3. **openai** - GPT-3.5-turbo
4. **glm** - GLM-4 (智谱AI)

## Files Updated

1. `pipeline/model_client.py` - Added GLM configuration to PROVIDER_CONFIG
2. `.env.example` - Added GLM_API_KEY and updated provider options
3. `ENV_SETUP.md` - Added GLM setup instructions

## Testing

All providers have been verified to work correctly:

- ✅ Provider configuration loaded successfully
- ✅ API key retrieval working
- ✅ Cost calculation functional
- ✅ Utility functions operational

## Switching Providers

Simply change `LLM_PROVIDER` in your `.env` file:

```bash
# Switch to GLM
LLM_PROVIDER=glm
GLM_API_KEY=your_glm_api_key_here

# Switch back to DeepSeek
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

The client will automatically use the new provider on next run.
