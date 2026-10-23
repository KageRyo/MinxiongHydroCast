from pathlib import Path

from PIL import Image, ImageSequence


def test_demo_walkthrough_is_decodable_animated_gif():
    path = Path(__file__).parents[1] / "docs" / "assets" / "demo-walkthrough.gif"
    with Image.open(path) as image:
        assert image.format == "GIF"
        assert image.is_animated
        for frame in ImageSequence.Iterator(image):
            frame.load()
