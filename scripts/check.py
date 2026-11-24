import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage
from apps.api.vision import config, grade_photo, normalize_photo
from apps.api.worker import check_items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("doctor", "contract", "live"))
    p.add_argument("--photo", type=Path)
    p.add_argument("--provider", choices=("OpenAI", "DeepSeek"))
    args = p.parse_args()
    if args.action == "doctor":
        from ml.dkt.inference import model_info

        print("DKT:", model_info())
        print("Python", sys.version.split()[0])
        print("Built UI:", (storage.ROOT / "apps/web/dist/index.html").is_file())
        for provider, _, model, key in config():
            print(provider, model, "configured" if key else "missing")
        return
    if args.action == "contract":
        from apps.api.main import app

        dest = storage.ROOT / "packages/contracts/openapi.json"
        dest.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
        events = storage.ROOT / "packages/contracts/events.schema.json"
        from apps.api.contracts import Event

        events.write_text(
            json.dumps(Event.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
        )
        return
    if not any(v[3] for v in config()):
        raise SystemExit(
            "Live check pending: configure a rotated backend provider key."
        )
    if args.photo:
        photo = normalize_photo(args.photo.read_bytes())[0]
        source = "operator-supplied worksheet"
    else:
        import io

        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (1200, 640), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=56)
        draw.text((75, 90), "1.  8 + 7 = 15", fill="black", font=font)
        draw.text((75, 320), "2.  9 - 4 = 8", fill="black", font=font)
        out = io.BytesIO()
        image.save(out, "JPEG", quality=95)
        photo = out.getvalue()
        source = "generated printed test input, separate from iPhone evidence"
    grade, meta = grade_photo(photo, only_provider=args.provider)
    rows = check_items(grade)
    if not rows:
        raise SystemExit("No worksheet items returned.")
    if not args.photo and [row["verdict"] for row in rows] != ["correct", "incorrect"]:
        raise SystemExit(
            "The real provider response disagreed with the smoke worksheet's answer key."
        )
    print(json.dumps({**meta, "items": len(rows), "input_source": source}, indent=2))


if __name__ == "__main__":
    main()
