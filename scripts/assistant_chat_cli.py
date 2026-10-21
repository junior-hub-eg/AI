"""Chat with the assistant in the terminal, as one of the mock students, before it is connected to the backend.

    python scripts/assistant_chat_cli.py                          # pick a persona
    python scripts/assistant_chat_cli.py --persona frontend_beginner
    python scripts/assistant_chat_cli.py --persona new_student --message "أبدأ منين؟"

Uses ASSISTANT_LLM_MODEL from .env ("fake" needs no key but only shows the wiring). Type /reset to clear the history,
/persona to switch student, /quit to leave.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant.assistant import Assistant  # noqa: E402
from assistant.config import get_settings  # noqa: E402
from assistant.llm import create_model  # noqa: E402
from assistant.schemas import HistoryItem, ReplyRequest  # noqa: E402

PERSONAS = ROOT / "assistant" / "mock" / "contexts"

if hasattr(sys.stdout, "reconfigure"):  # Arabic on Windows terminals
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")


def personas() -> list[str]:
    return sorted(p.stem for p in PERSONAS.glob("*.json"))


def choose() -> str:
    names = personas()
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}")
    pick = input("Persona number: ").strip()
    return names[int(pick) - 1] if pick.isdigit() and 0 < int(pick) <= len(names) else names[0]


async def ask(assistant: Assistant, persona: str, history: list[HistoryItem], message: str, debug: bool) -> str:
    context = json.loads((PERSONAS / f"{persona}.json").read_text(encoding="utf-8"))
    request = ReplyRequest(conversation_id=uuid.uuid4(), student_ref=uuid.uuid4(), message=message,
                           history=history[-20:], context=context)
    response, tools = await assistant.reply(request)
    print(f"\nAssistant: {response.reply}")
    if response.suggestions:
        print("  Suggestions: " + " | ".join(response.suggestions))
    if response.links:
        print("  Links: " + ", ".join(f"{link.kind}:{link.ref or '-'}" for link in response.links))
    if debug:
        print(f"  [topic={response.topic} tools={','.join(tools) or '-'} {response.meta.latency_ms} ms model={response.meta.model_id}]")
    print()
    return response.reply


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", choices=personas())
    parser.add_argument("--message")
    parser.add_argument("--quiet", action="store_true", help="hide topic, tools and latency")
    args = parser.parse_args()

    settings = get_settings()
    assistant = Assistant(create_model(settings), settings)
    persona = args.persona or choose()
    debug = not args.quiet
    history: list[HistoryItem] = []

    if args.message:
        await ask(assistant, persona, history, args.message, debug)
        return

    print(f"Chatting as '{persona}' with {settings.llm_model}. /reset /persona /quit\n")
    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            continue
        if message == "/quit":
            break
        if message == "/reset":
            history.clear()
            print("History cleared.\n")
            continue
        if message == "/persona":
            persona, history = choose(), []
            continue
        reply = await ask(assistant, persona, history, message, debug)
        history += [HistoryItem(role="student", text=message), HistoryItem(role="assistant", text=reply)]


if __name__ == "__main__":
    asyncio.run(main())
