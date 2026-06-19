"""Probe the Azure AI Foundry Anthropic (Claude) endpoint two ways:
  1. the raw anthropic SDK AnthropicFoundry client (the user's pattern)
  2. langchain_anthropic.ChatAnthropic with base_url (the integration we want)
so we learn the correct auth/base_url before wiring it into build_model_for().
Run: ~/joyjoy/backend/.venv/bin/python ~/joyjoy/scripts/test_foundry_anthropic.py
"""
import asyncio
import os

ENDPOINT = "https://swa-it-foundry-cs-ai.services.ai.azure.com/anthropic/"
ENDPOINT_NO_SLASH = "https://swa-it-foundry-cs-ai.services.ai.azure.com/anthropic"
MODEL = "claude-opus-4-7"
# Key is NOT committed — export AZURE_FOUNDRY_ANTHROPIC_API_KEY to run this probe.
KEY = os.environ.get("AZURE_FOUNDRY_ANTHROPIC_API_KEY", "")


def test_foundry():
    from anthropic import AnthropicFoundry
    client = AnthropicFoundry(api_key=KEY, base_url=ENDPOINT)
    msg = client.messages.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=32,
    )
    print("FOUNDRY OK ->", msg.content)


async def test_langchain_xapikey():
    from langchain_anthropic import ChatAnthropic
    m = ChatAnthropic(model=MODEL, api_key=KEY, base_url=ENDPOINT_NO_SLASH, max_tokens=32, timeout=30)
    r = await m.ainvoke("Reply with exactly: OK")
    print("LANGCHAIN (x-api-key) OK ->", r.content)


async def test_langchain_apikey_header():
    # Foundry may want the Azure 'api-key' header instead of anthropic 'x-api-key'.
    from langchain_anthropic import ChatAnthropic
    m = ChatAnthropic(
        model=MODEL, api_key=KEY, base_url=ENDPOINT_NO_SLASH,
        default_headers={"api-key": KEY}, max_tokens=32, timeout=30,
    )
    r = await m.ainvoke("Reply with exactly: OK")
    print("LANGCHAIN (api-key header) OK ->", r.content)


if __name__ == "__main__":
    for name, fn in [("foundry", test_foundry)]:
        try:
            fn()
        except Exception as e:
            print(f"{name} ERR ->", repr(e)[:400])
    for name, coro in [
        ("langchain x-api-key", test_langchain_xapikey),
        ("langchain api-key header", test_langchain_apikey_header),
    ]:
        try:
            asyncio.run(coro())
        except Exception as e:
            print(f"{name} ERR ->", repr(e)[:400])
