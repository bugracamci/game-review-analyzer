"""One small client for two LLM APIs: Google Gemini and Groq.

Every call says which provider, key and model to use, so each user runs on
their own API key. Errors are handled by type:
  429 (rate limit)        -> wait (using the server's hint) and retry
  429 (no free quota left)-> switch to the next fallback model
  503 / 5xx (overloaded)  -> switch model after two failures, else wait
  404 (model retired)     -> switch to the replacement named in the error
  400 / 401 / 403         -> stop: retrying cannot fix a bad key or request
"""
import hashlib
import json
import re
import time
from dataclasses import dataclass, field

import requests

import config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    """No model has quota left today - stop and resume later."""


class BadKey(LLMError):
    """The API key was rejected."""


@dataclass
class LLMConfig:
    api_key: str
    provider: str = "gemini"
    model: str = config.DEFAULT_GEMINI_MODEL
    fallbacks: list = field(default_factory=lambda: list(config.GEMINI_FALLBACK_MODELS))
    min_gap: float = config.MIN_SECONDS_BETWEEN_CALLS
    send_thinking: bool = True
    log: object = print            # where progress notes go (print or a UI callback)
    calls: int = 0                 # successful calls made with this config
    models_used: set = field(default_factory=set)


_last_call: dict[str, float] = {}


def _throttle(cfg: LLMConfig) -> None:
    key = hashlib.sha256(cfg.api_key.encode()).hexdigest()
    wait = cfg.min_gap - (time.time() - _last_call.get(key, 0))
    if wait > 0:
        time.sleep(wait)
    _last_call[key] = time.time()


def _retry_delay(response: requests.Response, attempt: int) -> float:
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header) + 1
        except ValueError:
            pass
    match = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', response.text)
    if match:
        return float(match.group(1)) + 1
    return min(5 * 2 ** attempt, 60)


def _switch_model(cfg: LLMConfig, reason: str) -> bool:
    while cfg.fallbacks:
        nxt = cfg.fallbacks.pop(0)
        if nxt != cfg.model:
            cfg.log(f"{cfg.model} {reason} – switching to {nxt}")
            cfg.model = nxt
            return True
    return False


def _call(cfg: LLMConfig, system: str, prompt: str) -> requests.Response:
    if cfg.provider == "groq":
        return requests.post(
            GROQ_URL, headers={"Authorization": f"Bearer {cfg.api_key}"}, timeout=120,
            json={"model": cfg.model, "temperature": 0.2,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]})
    generation = {"temperature": 0.2, "responseMimeType": "application/json"}
    if cfg.send_thinking:
        if "2.5-flash" in cfg.model:
            generation["thinkingConfig"] = {"thinkingBudget": 0}
        elif cfg.model.startswith("gemini-3"):
            generation["thinkingConfig"] = {"thinkingLevel": "low"}
    return requests.post(
        f"{GEMINI_URL}/{cfg.model}:generateContent",
        headers={"x-goog-api-key": cfg.api_key}, timeout=120,
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": prompt}]}],
              "generationConfig": generation})


def _extract(cfg: LLMConfig, data: dict) -> dict:
    if cfg.provider == "groq":
        text = data["choices"][0]["message"]["content"]
    else:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)


def complete_json(cfg: LLMConfig, system: str, prompt: str) -> dict:
    """Send one prompt and return the parsed JSON answer."""
    overloaded = 0
    for attempt in range(config.MAX_RETRIES + len(cfg.fallbacks)):
        _throttle(cfg)
        try:
            response = _call(cfg, system, prompt)
        except requests.RequestException as e:
            cfg.log(f"network error ({type(e).__name__}), retrying…")
            time.sleep(5)
            continue

        status, text = response.status_code, response.text
        if status == 200:
            try:
                result = _extract(cfg, response.json())
                cfg.calls += 1
                cfg.models_used.add(cfg.model)
                return result
            except (KeyError, IndexError, ValueError):
                cfg.log("model returned invalid JSON, retrying…")
                continue

        lower = text.lower()
        if status in (401, 403) or "api key not valid" in lower or "api_key_invalid" in lower:
            raise BadKey("The API key was rejected. Check it in Settings.")
        if status == 429:
            daily = "perday" in lower or "per day" in lower
            no_free = '"limit": 0' in text or "limit: 0" in text
            if daily or no_free:
                if cfg.provider == "gemini" and _switch_model(cfg, "has no free quota left"):
                    continue
                raise QuotaExhausted("Daily quota used up for every model. "
                                     "Progress is saved – continue tomorrow.")
            wait = _retry_delay(response, attempt)
            cfg.log(f"rate limit – waiting {wait:.0f}s")
            time.sleep(wait)
            continue
        if status >= 500:
            overloaded += 1
            if overloaded >= 2 and cfg.provider == "gemini" and \
                    _switch_model(cfg, f"is overloaded ({status})"):
                overloaded = 0
                continue
            time.sleep(_retry_delay(response, attempt))
            continue
        if status == 400 and "thinking" in lower and cfg.send_thinking:
            cfg.send_thinking = False
            continue
        retired = re.search(r"no longer available.*?use models/([\w.-]+)", text)
        if status == 404 and retired and cfg.provider == "gemini":
            cfg.log(f"{cfg.model} is retired – switching to {retired.group(1)}")
            cfg.model = retired.group(1)
            continue
        if status == 404 and cfg.provider == "gemini" and _switch_model(cfg, "is not available"):
            continue
        raise LLMError(f"HTTP {status}: {text[:300]}")
    raise LLMError("Gave up after several attempts.")


def list_gemini_models(api_key: str) -> list[str]:
    """Models this key can use for text generation (also a cheap key check)."""
    r = requests.get(GEMINI_URL, headers={"x-goog-api-key": api_key},
                     params={"pageSize": 200}, timeout=30)
    if r.status_code in (400, 401, 403):
        raise BadKey("The API key was rejected.")
    r.raise_for_status()
    return sorted(m["name"].removeprefix("models/") for m in r.json().get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", [])
                  and "gemini" in m["name"] and not any(
                      x in m["name"] for x in ("tts", "image", "embedding", "audio")))
