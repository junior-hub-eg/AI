"""Run a whole interview against a running service (real or mock) and print it.

    python scripts/smoke_test.py                       # http://127.0.0.1:8000
    python scripts/smoke_test.py --url http://127.0.0.1:8001 --questions 5
    python scripts/smoke_test.py --audio my_answer.webm --mime audio/webm

Set TOKEN=<jwt> in the environment when auth is enabled (see make_dev_token.py).
"""

import argparse
import base64
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playground.sample_data import ANSWERS, TRACKS


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--questions", type=int, default=6)
    p.add_argument("--audio")
    p.add_argument("--mime", default="audio/webm")
    p.add_argument("--no-speak", action="store_true")
    args = p.parse_args()

    headers = {"Authorization": f"Bearer {os.environ['TOKEN']}"} if os.getenv("TOKEN") else {}
    base = {
        "interview_id": str(uuid.uuid4()),
        "student_ref": "stu_smoke",
        "grade": 8,
        "tracks": TRACKS,
        "max_questions": args.questions,
        "speak": not args.no_speak,
    }
    history: list[dict] = []

    with httpx.Client(base_url=args.url, headers=headers, timeout=40) as http:

        def call(path: str, body: dict) -> dict:
            started = time.perf_counter()
            r = http.post(path, json=body)
            print(f"  [{r.status_code}] {path} in {time.perf_counter() - started:.1f}s")
            r.raise_for_status()
            return r.json()

        reply = call("/v1/discovery/turns", {**base, "history": history, "answer": None})
        while not reply["finished"]:
            q = reply["next_question"]
            print(
                f"\nQ{q['order_index']}: {q['question_text']}"
                f"   (audio: {'yes' if q['audio_base64'] else 'no'})"
            )
            answer = {"order_index": q["order_index"], "question_text": q["question_text"]}
            if args.audio and q["order_index"] == 2:
                answer["audio_base64"] = base64.b64encode(Path(args.audio).read_bytes()).decode()
                answer["audio_mime_type"] = args.mime
            else:
                answer["transcript"] = ANSWERS[(q["order_index"] - 1) % len(ANSWERS)]
            reply = call("/v1/discovery/turns", {**base, "history": history, "answer": answer})
            done = reply["answered"]
            print(f"A{done['order_index']}: {done['transcript']}")
            history.append(
                {
                    "order_index": done["order_index"],
                    "question_text": answer["question_text"],
                    "transcript": done["transcript"],
                }
            )

        print("\nFinished. Asking for the result...")
        result = call(
            "/v1/discovery/results",
            {k: v for k, v in base.items() if k not in ("max_questions", "speak")} | {"responses": history},
        )
        for rec in result["recommendations"]:
            print(f"  #{rec['rank']} {rec['track_code']:9} {rec['match_percent']:3}%  {rec['reason']}")
        print(f"\nSummary: {result['summary']}\nModel: {result['meta']['model_id']}")


if __name__ == "__main__":
    main()
