"""Claude client: one streaming call, cost math. Everything returned is plain dicts."""
from typing import Awaitable, Callable

import anthropic

from . import config

Emit = Callable[[dict], Awaitable[None]]


def cost_of(model: str, usage: dict) -> float:
    pin, pout, pread, pwrite = config.PRICING.get(model, config.PRICING["claude-opus-5-5"])
    return (
        usage.get("input_tokens", 0) * pin
        + usage.get("output_tokens", 0) * pout
        + (usage.get("cache_read_input_tokens") or 0) * pread
        + (usage.get("cache_creation_input_tokens") or 0) * pwrite
    ) / 1_000_000


class LLM:
    """Real Claude calls. Tests swap in a fake with the same `stream` method."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic()

    async def stream(self, *, model: str, effort: str, system: list, tools: list,
                     messages: list, emit: Emit) -> dict:
        kwargs = dict(
            model=model,
            max_tokens=32000,
            system=system,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
        )
        if model in config.FALLBACK_MODELS:
            api = self.client.beta.messages
            kwargs.update(betas=[config.FALLBACK_BETA], fallbacks="default")
        else:
            api = self.client.messages

        async with api.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    await emit({"type": "block_start", "block_type": event.content_block.type,
                                "name": getattr(event.content_block, "name", None)})
                elif event.type == "content_block_delta":
                    d = event.delta
                    if d.type == "text_delta":
                        await emit({"type": "text_delta", "text": d.text})
                    elif d.type == "thinking_delta":
                        await emit({"type": "thinking_delta", "text": d.thinking})
            final = await stream.get_final_message()

        msg = final.to_dict()
        return {
            "content": msg["content"],
            "stop_reason": msg.get("stop_reason"),
            "usage": msg.get("usage") or {},
            "model": msg.get("model", model),
        }
