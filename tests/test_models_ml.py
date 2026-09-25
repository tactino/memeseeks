import pytest
from PIL import Image, ImageDraw, ImageFont

pytestmark = pytest.mark.ml


def _text_image(text, size=(480, 140)):
    im = Image.new("RGB", size, "white")
    ImageDraw.Draw(im).text((20, 30), text, fill="black", font=ImageFont.load_default(size=56))
    return im


def test_ocr_reads_rendered_text():
    from memeseeks.models.ocr import RapidOcr, ocr_text
    assert "HELLO" in ocr_text(RapidOcr()(_text_image("HELLO 2026"))).upper().replace(" ", "")


def test_ocr_blank_image_returns_no_lines():
    from memeseeks.models.ocr import RapidOcr
    assert RapidOcr()(Image.new("RGB", (200, 200), "white")) == []


def test_chinese_clip_prefers_matching_colour():
    from memeseeks.models.clip import ChineseClip
    clip = ChineseClip()
    img = clip.embed_images([Image.new("RGB", (224, 224), (220, 20, 20))])[0]
    texts = clip.embed_texts(["一张红色的图片", "一张蓝色的图片"])
    assert texts[0] @ img > texts[1] @ img


def test_bge_m3_is_cross_lingual():
    from memeseeks.models.textembed import BgeM3
    e = BgeM3().embed(["一只猫", "a cat", "一辆汽车"])
    assert e[0] @ e[1] > e[0] @ e[2]


def test_qwen_vl_describes_image_as_json():
    from memeseeks.models.vlm import QwenVl
    d = QwenVl().describe(_text_image("WOW"))
    assert "_raw" not in d and "画面" in d
