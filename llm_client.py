"""One small wrapper around two free LLM APIs: Google Gemini and Groq.

The rest of the project only calls `complete_json(system, prompt)`.
Switching provider = changing LLM_PROVIDER in .env. Nothing else.

Plain HTTP (requests) is used instead of the vendor SDKs so both providers
look the same in code and there are fewer dependencies.

Run `python llm_client.py` to test your key and see the available models.
"""
import json
import re
import time

import requests

import config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_last_call = 0.0
_send_thinking_config = True  # turned off if the model rejects it
_fallbacks = list(config.GEMINI_FALLBACK_MODELS)


def _switch_gemini_model(reason: str) -> bool:
    """Move to the next fallback Gemini model. Returns False if none are left."""
    while _fallbacks:
        nxt = _fallbacks.pop(0)
        if nxt != config.GEMINI_MODEL:
            print(f"    NOTE: {config.GEMINI_MODEL} {reason} - switching to {nxt}")
            config.GEMINI_MODEL = nxt
            return True
    return False


class LLMError(RuntimeError):
    pass


class DailyQuotaExceeded(LLMError):
    """Retrying won't help today - switch provider or wait until tomorrow."""


def model_name() -> str:
    return config.GEMINI_MODEL if config.LLM_PROVIDER == "gemini" else config.GROQ_MODEL


def _throttle():
    """Keep a minimum gap between calls so we stay under per-minute limits."""
    global _last_call
    wait = config.MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _retry_delay(response: requests.Response, attempt: int) -> float:
    """How long to wait before retrying: use the server's hint if it gives one."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header) + 1
        except ValueError:
            pass
    match = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', response.text)
    if match:
        return float(match.group(1)) + 1
    return min(5 * 2 ** attempt, 120)  # 5s, 10s, 20s, 40s, 80s, 120s


def _call_gemini(system: str, prompt: str) -> requests.Response:
    if not config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is missing. Add it to your .env file.")
    generation = {"temperature": 0.2, "responseMimeType": "application/json"}
    if not _send_thinking_config:
        pass
    elif "2.5-flash" in config.GEMINI_MODEL:
        # Turn off 'thinking' for this simple labeling task: faster, uses less quota.
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    elif config.GEMINI_MODEL.startswith("gemini-3"):
        generation["thinkingConfig"] = {"thinkingLevel": "low"}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation,
    }
    return requests.post(
        f"{GEMINI_URL}/{config.GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": config.GEMINI_API_KEY},
        json=body,
        timeout=120,
    )


def _call_groq(system: str, prompt: str) -> requests.Response:
    if not config.GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is missing. Add it to your .env file.")
    body = {
        "model": config.GROQ_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    return requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json=body,
        timeout=120,
    )


def _extract_text(data: dict) -> str:
    if config.LLM_PROVIDER == "gemini":
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    return data["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # remove markdown fences
    return json.loads(text)


def complete_json(system: str, prompt: str) -> dict:
    """Send a prompt, get back parsed JSON. Waits and retries on 429 / 5xx errors."""
    global _send_thinking_config
    call = _call_gemini if config.LLM_PROVIDER == "gemini" else _call_groq
    overloaded = 0
    for attempt in range(config.MAX_RETRIES):
        _throttle()
        try:
            response = call(system, prompt)
        except requests.RequestException as e:
            print(f"    network error ({type(e).__name__}), retrying...")
            time.sleep(5 * (attempt + 1))
            continue

        if response.status_code == 200:
            try:
                return _parse_json(_extract_text(response.json()))
            except (KeyError, IndexError, ValueError):
                print("    model returned invalid JSON, retrying...")
                continue

        if response.status_code == 429:
            text = response.text.lower()
            daily = "perday" in text or "per day" in text
            no_free_quota = '"limit": 0' in text or "limit: 0" in text
            if config.LLM_PROVIDER == "gemini" and (daily or no_free_quota):
                if _switch_gemini_model("has no free quota left"):
                    continue
            if daily:
                raise DailyQuotaExceeded(
                    "Daily free quota used up. Wait until tomorrow, or set "
                    "LLM_PROVIDER=groq in .env to continue with Groq."
                )
            wait = _retry_delay(response, attempt)
            print(f"    rate limit (429) - waiting {wait:.0f}s then retrying...")
            time.sleep(wait)
            continue

        if response.status_code >= 500:
            overloaded += 1
            if (overloaded >= 2 and config.LLM_PROVIDER == "gemini"
                    and _switch_gemini_model(f"is overloaded ({response.status_code})")):
                overloaded = 0
                continue
            wait = _retry_delay(response, attempt)
            print(f"    server error {response.status_code} - waiting {wait:.0f}s...")
            time.sleep(wait)
            continue

        # Some models don't accept the thinking setting - drop it and retry.
        if response.status_code == 400 and "thinking" in response.text.lower() and _send_thinking_config:
            _send_thinking_config = False
            continue

        # Retired model: Google's error names the replacement - switch to it once.
        retired = re.search(r"no longer available.*?use models/([\w.-]+)", response.text)
        if response.status_code == 404 and retired and config.LLM_PROVIDER == "gemini":
            print(f"    NOTE: {config.GEMINI_MODEL} is retired, switching to {retired.group(1)}. "
                  f"Update GEMINI_MODEL in .env to make this permanent.")
            config.GEMINI_MODEL = retired.group(1)
            if retired.group(1) in _fallbacks:
                _fallbacks.remove(retired.group(1))
            continue

        # 400 / 401 / 403 / 404: retrying will not fix these.
        raise LLMError(f"HTTP {response.status_code}: {response.text[:500]}")

    raise LLMError(f"Gave up after {config.MAX_RETRIES} attempts.")


def list_gemini_models() -> list[str]:
    r = requests.get(GEMINI_URL, headers={"x-goog-api-key": config.GEMINI_API_KEY},
                     params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    return [m["name"].removeprefix("models/") for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


if __name__ == "__main__":
    print(f"Provider: {config.LLM_PROVIDER} | model: {model_name()}")
    if config.LLM_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        flash = [m for m in list_gemini_models() if "flash" in m]
        print("Flash models your key can use:", ", ".join(flash))
    result = complete_json(
        "You answer only with JSON.",
        'Classify the sentiment of: "Great game but too many ads". '
        'Return {"sentiment": "positive|neutral|negative"}',
    )
    print("Test call OK ->", result)
