"""Create a multi-resolution Windows icon for the Attendance-Sight executable."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def create_icon(output: Path) -> None:
    scale = 4
    size = 256
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def coords(*values: int) -> tuple[int, ...]:
        return tuple(value * scale for value in values)

    draw.rounded_rectangle(coords(8, 8, 248, 248), radius=68 * scale, fill="#0F172A")
    draw.ellipse(coords(43, 43, 213, 213), outline="#38BDF8", width=9 * scale)
    draw.ellipse(coords(103, 78, 153, 128), fill="#E0F2FE")
    draw.arc(coords(76, 110, 180, 203), start=190, end=350, fill="#E0F2FE", width=13 * scale)
    draw.line([coords(165, 73), coords(181, 89), coords(211, 52)], fill="#34D399", width=12 * scale, joint="curve")

    image = image.resize((size, size), Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    create_icon(parser.parse_args().output)
