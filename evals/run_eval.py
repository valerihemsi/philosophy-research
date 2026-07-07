#!/usr/bin/env python
"""
Eval koşucusu — sabit soru seti üzerinde pipeline'ı çalıştırır, çıktıları
evals/results/<timestamp>/ altına markdown olarak kaydeder.

Kullanım:
    python evals/run_eval.py        # ilk 3 soru (hızlı duman testi)
    python evals/run_eval.py 10     # ilk 10 soru (tam set)

Karşılaştırma: iki koşunun results klasörlerini diff'leyerek ya da okuyarak
pipeline değişikliğinin çıktı kalitesini nasıl etkilediğine bak.
"""
import json
import queue
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from server import run_pipeline_thread  # noqa: E402

STAGE_NAMES = [
    "savunucu-a", "savunucu-b", "kor-elestirmen",
    "sentez", "curutme", "nihai-sentez",
]


def run_one(question: str, out_dir: Path) -> bool:
    msg_queue: queue.Queue = queue.Queue()
    outputs: dict[int, str] = {}
    rubric = None

    import threading
    t = threading.Thread(
        target=run_pipeline_thread, args=(question, msg_queue), daemon=True)
    t.start()

    while True:
        msg = msg_queue.get()
        if msg["type"] == "task_complete":
            outputs[msg["task_index"]] = msg["output"]
            print(f"    ✓ {STAGE_NAMES[msg['task_index']]}")
        elif msg["type"] == "rubric":
            rubric = msg["data"]
        elif msg["type"] == "done":
            break
        elif msg["type"] == "error":
            print(f"    ✗ HATA: {msg['message']}")
            return False

    slug = "".join(c if c.isalnum() else "-" for c in question.lower())[:50].strip("-")
    q_dir = out_dir / slug
    q_dir.mkdir(parents=True, exist_ok=True)
    for idx, name in enumerate(STAGE_NAMES):
        if idx in outputs:
            (q_dir / f"{idx}-{name}.md").write_text(outputs[idx])
    if rubric:
        (q_dir / "rubric.json").write_text(
            json.dumps(rubric, ensure_ascii=False, indent=2))
    return True


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    questions = json.loads(
        (Path(__file__).parent / "questions.json").read_text())["questions"][:n]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(__file__).parent / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Eval: {len(questions)} soru → {out_dir}\n")

    ok = 0
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q}")
        if run_one(q, out_dir):
            ok += 1
    print(f"\nBitti: {ok}/{len(questions)} başarılı → {out_dir}")


if __name__ == "__main__":
    main()
