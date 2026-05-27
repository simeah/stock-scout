"""
core/llm.py
===========
Unified LLM interface for Claude (Anthropic), Gemini (Google), and GPT-4 (OpenAI).
"""

import json


def llm_call(
    prompt: str,
    system: str = "",
    provider: str = "anthropic",
    api_key: str = "",
    max_tokens: int = 2048,
) -> str:
    """
    Call an LLM with unified interface.
    provider: "anthropic" | "gemini" | "openai"
    """
    if provider == "anthropic":
        return _claude_call(prompt, system, api_key, max_tokens)
    elif provider == "gemini":
        return _gemini_call(prompt, system, api_key, max_tokens)
    elif provider == "openai":
        return _openai_call(prompt, system, api_key, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def llm_json(
    prompt: str,
    system: str = "",
    provider: str = "anthropic",
    api_key: str = "",
    max_tokens: int = 8096,
) -> dict | list:
    """Call LLM expecting JSON response."""
    response = llm_call(prompt, system, provider, api_key, max_tokens)
    response = response.strip()
    if response.startswith("```"):
        response = response.split("```")[1]
        if response.startswith("json"):
            response = response[4:]
    response = response.strip()
    return json.loads(response)


def _claude_call(prompt: str, system: str, api_key: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=max_tokens,
        system=system or None,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _gemini_call(prompt: str, system: str, api_key: str, max_tokens: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=system or None,
    )
    response = model.generate_content(prompt)
    return response.text


def _openai_call(prompt: str, system: str, api_key: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    msg = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=max_tokens,
        messages=messages,
    )
    return msg.choices[0].message.content
