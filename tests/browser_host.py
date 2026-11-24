"""Isolated browser test server. Never uses production storage or a paid provider."""

import io
import os
import sys
import tempfile
from pathlib import Path
from threading import Event, Thread

import uvicorn
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import Response

from apps.api import storage, worker
from apps.api.main import app
from apps.api.vision import Grade


@app.get("/__fixture__/page")
def page():
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), "#ffeedd").save(buf, "JPEG")
    return Response(buf.getvalue(), media_type="image/jpeg")


def grade_fixture(photo):
    return Grade.model_validate(
        {
            "items": [
                {
                    "question": "1/3 + 1/6",
                    "student_answer": "2/9",
                    "reference_answer": "1/2",
                    "skill": "fractions",
                    "verdict": "incorrect",
                    "hints": ["先找到这两个分母的公倍数。", "将三分之一写成六分之几？"],
                    "explanation": "三分之一是六分之二，加六分之一得到二分之一。",
                    "review_reason": "",
                }
            ]
        }
    ), {
        "provider": "Browser fixture",
        "model": "test only",
        "request_id": "test-only",
        "usage": {},
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="lumiread-browser-fixture-") as folder:
        os.environ["LUMIREAD_VAR"] = folder
        os.environ["LUMIREAD_PHONE_ORIGIN"] = "http://127.0.0.1:8749"
        storage.initialize()
        done = Event()

        def work():
            while not done.is_set():
                if not worker.run_one(grade_fixture):
                    done.wait(0.05)

        proc = Thread(target=work, daemon=True)
        proc.start()
        try:
            uvicorn.run(
                app, host="127.0.0.1", port=8749, access_log=False, proxy_headers=False
            )
        finally:
            done.set()
            proc.join(5)
