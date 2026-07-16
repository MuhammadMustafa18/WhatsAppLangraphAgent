"""Inspect a thread's checkpoint history.

Usage:
    .venv/Scripts/python.exe scripts/inspect_thread.py 923178761858@c.us
    .venv/Scripts/python.exe scripts/inspect_thread.py smoke@test.c.us --messages
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import build_graph


async def show(thread_id: str, show_messages: bool) -> None:
    g = await build_graph()
    cfg = {"configurable": {"thread_id": thread_id}}

    snap = await g.aget_state(cfg)
    if not snap.values:
        print(f"(no history for thread_id={thread_id!r})")
        return

    print(f"=== current state ({thread_id}) ===")
    for k, v in snap.values.items():
        if isinstance(v, list):
            print(f"  {k}: list[{len(v)}]")
        else:
            preview = repr(v)
            if len(preview) > 200:
                preview = preview[:200] + "…"
            print(f"  {k}: {preview}")

    if show_messages:
        print("\n=== messages ===")
        for m in snap.values.get("messages", []):
            print(f"  [{m['role']}] {m['content']}")

    print("\n=== checkpoint history (newest -> oldest) ===")
    print(f"  {'ckpt':<10} {'next':<20} {'msgs':<5} {'reply':<60}")
    async for s in g.aget_state_history(cfg):
        cid = s.config["configurable"]["checkpoint_id"][:8]
        next_ = ",".join(s.next) if s.next else "(end)"
        msgs = len(s.values.get("messages", []))
        reply = (s.values.get("reply") or "")[:55].replace("\n", " ")
        print(f"  {cid:<10} {next_:<20} {msgs:<5} {reply}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("thread_id", help="chat_id / thread_id, e.g. 923178761858@c.us")
    p.add_argument(
        "--messages", "-m", action="store_true",
        help="dump the full messages list at the current state",
    )
    args = p.parse_args()
    asyncio.run(show(args.thread_id, args.messages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())