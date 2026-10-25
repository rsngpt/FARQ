"""Convert OpenAI's Whisper large-v3-turbo to CTranslate2 format for faster-whisper.

We convert the official weights ourselves (instead of downloading someone
else's conversion) so every weight we run comes straight from the declared
model. The output folder gets a PROVENANCE.json: source repo and exact commit,
tool versions, and a SHA-256 of every file.

Run once per machine (about 1.6 GB download), from the repo root:

    uv run --no-project --with ctranslate2==4.8.2 --with transformers==5.20.1 \
        --with torch==2.14.0 --with huggingface-hub python scripts/convert_whisper.py

Output: models/whisper-large-v3-turbo-ct2/ (git-ignored).
"""

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import ctranslate2
import transformers
from ctranslate2.converters import TransformersConverter
from huggingface_hub import HfApi, snapshot_download

SOURCE = "openai/whisper-large-v3-turbo"
OUT = Path(__file__).resolve().parents[1] / "models" / "whisper-large-v3-turbo-ct2"
# Stored as float16; faster-whisper can load it as int8 to save GPU memory.
QUANTIZATION = "float16"
# Tokenizer and audio settings faster-whisper reads at load time.
COPY_FILES = ["tokenizer.json", "preprocessor_config.json"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if OUT.exists():
        print(f"{OUT} already exists; delete it first to convert again.")
        return 1

    revision = HfApi().model_info(SOURCE).sha
    print(f"Downloading {SOURCE} at commit {revision} ...")
    source_dir = Path(
        snapshot_download(
            SOURCE,
            revision=revision,
            allow_patterns=["*.json", "*.safetensors", "*.txt"],
        )
    )

    tmp = OUT.with_name(OUT.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Converting to CTranslate2 ({QUANTIZATION}) ...")
    TransformersConverter(str(source_dir), copy_files=COPY_FILES).convert(
        str(tmp), quantization=QUANTIZATION
    )

    files = {p.name: sha256(p) for p in sorted(tmp.iterdir()) if p.is_file()}
    provenance = {
        "source": f"https://huggingface.co/{SOURCE}",
        "source_revision": revision,
        "converted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "quantization": QUANTIZATION,
        "tools": {
            "ctranslate2": ctranslate2.__version__,
            "transformers": transformers.__version__,
            "python": sys.version.split()[0],
        },
        "sha256": files,
    }
    (tmp / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")
    tmp.rename(OUT)
    size_mb = sum((OUT / name).stat().st_size for name in files) / 1e6
    print(f"Done: {OUT} ({size_mb:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
