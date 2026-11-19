import base64
import logging
from typing import Optional

import aiohttp

from ..config import settings

log = logging.getLogger("kayra.ai")

TIMEOUT = aiohttp.ClientTimeout(total=10, sock_connect=5, sock_read=8)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.8-flash:generateContent"
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

FALLBACK_MSG = (
    "Arre yaar, thoda busy hoon abhi 😅 Thodi der baad try karo — "
    "I'll be right here bestie! (AI providers temporarily unavailable)"
)


class AllProvidersFailed(Exception):
    pass


class AIClient:
    def __init__(self) -> None:
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=TIMEOUT)

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    # ---------- public API ----------

    async def chat(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int = 700,
    ) -> str:
        """Try providers in order: Gemini -> Groq -> OpenRouter."""
        if self.session is None:
            await self.start()

        errors: list[str] = []
        providers = []
        # fastest first: Groq is quickest, Gemini next, OpenRouter last
        if settings.groq_key:
            providers.append(
                ("groq", self._openai, (messages, system, max_tokens, settings.groq_key, GROQ_URL, settings.groq_model))
            )
        if settings.gemini_key:
            providers.append(("gemini", self._gemini, (messages, system, max_tokens)))
        if settings.openrouter_key:
            providers.append(
                (
                    "openrouter",
                    self._openai,
                    (messages, system, max_tokens, settings.openrouter_key, OPENROUTER_URL, settings.openrouter_model),
                )
            )

        if not providers:
            return (
                "⚠️ Koi AI API key set nahi hai! (.env mein GEMINI_API_KEY / "
                "GROQ_API_KEY / OPENROUTER_API_KEY daalo) — abhi main sirf commands "
                "se baat kar sakta hoon 😅"
            )

        for name, fn, args in providers:
            try:
                reply = await fn(*args)
                if reply:
                    return reply.strip()
                errors.append(f"{name}: empty reply")
            except Exception as e:  # noqa: BLE001
                log.warning("provider %s failed: %s", name, e)
                errors.append(f"{name}: {e}")

        log.error("all providers failed: %s", errors)
        return FALLBACK_MSG

    async def vision(self, image_bytes: bytes, mime: str, prompt: str) -> str:
        """Gemini-only vision call (OCR etc). Falls back to message if no key."""
        if not settings.gemini_key:
            return "⚠️ OCR ke liye GEMINI_API_KEY chahiye (.env mein set karo)."
        if self.session is None or self.session.closed:
            await self.start()
        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": mime, "data": b64}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": 800},
        }
        async with self.session.post(
            GEMINI_URL + f"?key={settings.gemini_key}", json=payload
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"gemini vision HTTP {resp.status}: {await resp.text()}")
            data = await resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            return "Image samajh nahi aayi 😅 dobara bhejo."

    # ---------- providers ----------

    async def _gemini(self, messages: list[dict], system: str, max_tokens: int) -> str:
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9},
        }
        async with self.session.post(
            GEMINI_URL + f"?key={settings.gemini_key}", json=payload
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {(await resp.text())[:200]}")
            data = await resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"bad gemini response: {data}") from e

    async def _openai(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int,
        key: str,
        url: str,
        model: str,
    ) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "temperature": 0.9,
        }
        headers = {"Authorization": f"Bearer {key}"}
        async with self.session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {(await resp.text())[:200]}")
            data = await resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"bad response: {data}") from e


ai_client = AIClient()
