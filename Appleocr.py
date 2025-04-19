import argparse
import json
import logging
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
from typing import Tuple

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch OCR with AppleOCRTool")
    parser.add_argument(
        "-i", "--input",
        default="images",
        help="input image folder"
    )
    parser.add_argument(
        "-e", "--error",
        default="error_images",
        help="folder to move images that failed OCR"
    )
    parser.add_argument(
        "-o", "--output",
        default="ocr_results.json",
        help="output JSON file"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        default=10,
        help="timeout in seconds per image"
    )
    parser.add_argument(
        "-n", "--threads",
        type=int,
        default=6,
        help="Change it as you like, I set it as 6"
    )
    parser.add_argument(
        "-c", "--tool",
        default="AppleOCRTool",
        help="path to the OCR CLI tool (relative or absolute)"
    )
    return parser.parse_args()

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def locate_and_prepare_tool(tool_arg: str) -> Path:
    """
    Given the --tool argument, return an absolute executable path.
    If the file does not exist or is not executable, attempt to add +x permission.
    """
    p = Path(tool_arg)
    # If the path is not absolute, try script directory first, then cwd
    if not p.is_absolute():
        script_dir = Path(__file__).resolve().parent
        candidate = script_dir / p
        if candidate.exists():
            p = candidate
        else:
            cwd_candidate = Path.cwd() / p
            if cwd_candidate.exists():
                p = cwd_candidate
    p = p.resolve()

    if not p.exists() or not p.is_file():
        logging.error(f"OCR tool not found: {p}")
        sys.exit(1)

    # Ensure executable permission
    mode = p.stat().st_mode
    if not (mode & stat.S_IXUSR):
        logging.info(f"Adding execute permission to {p.name}")
        p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return p

def process_image(
    image_path: Path,
    tool_path: Path,
    timeout: int
) -> Tuple[str, str, float, bool]:
    """
    Invoke the OCR tool on a single image.
    Returns: (image_name, text, confidence, is_error)
    """
    image_name = image_path.stem
    try:
        cp = subprocess.run(
            [str(tool_path), str(image_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            check=True
        )
        lines = cp.stdout.strip().splitlines()
        # If the last line is like "───Confidence:0.8734", parse it
        if lines and lines[-1].startswith("───Confidence:"):
            conf = float(lines[-1].split(":", 1)[1])
            text = "\n".join(lines[:-1]).strip()
        else:
            text = "\n".join(lines).strip()
            conf = 1.0 if text else 0.0

    except subprocess.TimeoutExpired:
        logging.error(f"OCR timeout: {image_path.name}")
        text, conf = "", 0.0
    except subprocess.CalledProcessError as e:
        logging.error(f"OCR failed ({image_path.name}): {e.stderr.strip()}")
        text, conf = "", 0.0
    except Exception as e:
        logging.error(f"Unknown error ({image_path.name}): {e}")
        text, conf = "", 0.0

    is_error = (conf == 0.0)
    return image_name, text, conf, is_error

def main():
    args = parse_args()
    setup_logging()

    # Prepare paths
    input_dir   = Path(args.input)
    error_dir   = Path(args.error)
    output_file = Path(args.output)
    tool_path   = locate_and_prepare_tool(args.tool)

    input_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    # Collect all PNG files
    image_files = list(input_dir.glob("*.png"))
    if not image_files:
        logging.warning(f"No PNG images found in {input_dir}")
        sys.exit(0)

    results = {}

    # Run OCR in parallel
    with ProcessPoolExecutor(max_workers=args.threads) as executor:
        futures = executor.map(
            process_image,
            image_files,
            [tool_path] * len(image_files),
            [args.timeout] * len(image_files)
        )
        for image_name, text, conf, is_error in tqdm(
            futures,
            total=len(image_files),
            desc="Processing images"
        ):
            if is_error:
                shutil.copy(input_dir / f"{image_name}.png",
                            error_dir / f"{image_name}.png")
            results[image_name] = {
                "text":       text,
                "confidence": round(conf, 4)
            }

    # Sort by confidence and write JSON
    sorted_items = sorted(
        results.items(),
        key=lambda kv: kv[1]["confidence"],
        reverse=True
    )
    sorted_results = {k: v for k, v in sorted_items}

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(sorted_results, f, ensure_ascii=False, indent=4)

    logging.info(f"OCR completed, results saved to {output_file}")

if __name__ == "__main__":
    main()