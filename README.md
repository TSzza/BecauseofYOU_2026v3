# Because of YOU v3

LLM-driven campus narrative research demo with a three-Agent data flow:

```text
Designer -> Controller -> Critic
```

The story covers only the first semester of Grade 10 plus winter vacation: September to January. The total turn count is decided by Designer for each run, but must be greater than 60 so the design can cover the 60 original MSSMHS questionnaire items.

## Model Config

Model settings are source-code based. Edit:

```text
backend/config.py
```

Then fill `MODEL_SETTINGS`:

```python
MODEL_SETTINGS = {
    "provider": "openai",
    "model": "gpt-5-mini",
    "api_key": "YOUR_API_KEY_HERE",
    "base_url": "https://api.openai.com/v1",
    "failure_policy": "raise",
}
```

For DeepSeek-compatible mode:

```python
MODEL_SETTINGS = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": "YOUR_DEEPSEEK_API_KEY_HERE",
    "base_url": "https://api.deepseek.com/v1",
    "failure_policy": "raise",
}
```

For offline UI/debug mode:

```python
MODEL_SETTINGS = {
    "provider": "mock",
    "model": "mock",
    "api_key": "",
    "base_url": "",
    "failure_policy": "raise",
}
```

`ALLOW_ENV_OVERRIDE` is `False` by default, so environment variables will not silently replace the source-code settings.

## Prompts

Runtime prompts are YAML files:

- `prompts/designer.yaml`
- `prompts/controller.yaml`
- `prompts/critic.yaml`

`backend/prompt_loader.py` reads the `system: |` block from each YAML file. Agent inputs are passed as structured JSON user messages.

## Start App

```powershell
python backend\app.py
```

Then open:

```text
http://127.0.0.1:8765
```
