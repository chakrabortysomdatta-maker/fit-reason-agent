"""Read new returns and tickets, title issues, and suggest replies.  Usage: python scripts/run_pipeline.py [draft_limit]"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.pipeline import connect, draft_replies, tag_new_items, title_issues  # noqa: E402

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    t = time.time()
    print("0/3 stages ", connect().execute("select refresh_order_stages() as n").fetchone()["n"], "orders")
    print("1/3 tagging", tag_new_items())
    print("2/3 titles ", title_issues())
    print("3/3 replies", draft_replies(limit))
    print(f"done in {time.time() - t:.0f}s")
