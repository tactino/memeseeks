from memeseeks.models.ocr import OcrLine, ocr_text
from memeseeks.models.vlm import description_text, parse_json_object


def test_parse_json_object_from_fenced_reply():
    raw = '好的：\n```json\n{"画面": "一只猫", "情绪": "无语", "适用场景": ["对方说了离谱的话"]}\n```'
    assert parse_json_object(raw)["画面"] == "一只猫"


def test_parse_json_object_falls_back_to_raw():
    assert parse_json_object("我看不清这张图") == {"_raw": "我看不清这张图"}


def test_description_text_joins_fields_in_order_and_handles_raw():
    d = {"画面": "猫", "文字": "", "主题": ["熬夜", "上班"], "笑点": "越忙越想摸鱼", "情绪": "无奈", "梗": ""}
    assert description_text(d) == "画面：猫 主题：熬夜；上班 笑点：越忙越想摸鱼 情绪：无奈"
    assert description_text({"_raw": "一只猫"}) == "一只猫"


def test_describe_prompt_targets_meme_images_not_chat_stickers():
    from memeseeks.models.vlm import DESCRIBE_PROMPT
    assert '"主题"' in DESCRIBE_PROMPT and '"笑点"' in DESCRIBE_PROMPT
    assert "聊天" not in DESCRIBE_PROMPT


def test_ocr_text_joins_lines():
    assert ocr_text([OcrLine("你好", [], 0.9), OcrLine("世界", [], 0.9)]) == "你好 世界"


def test_rapid_ocr_skips_the_angle_classifier():
    from PIL import Image

    from memeseeks.models.ocr import RapidOcr
    calls = {}

    class Engine:
        def __call__(self, img, **kw):
            calls.update(kw)
            return None, None

    ocr = RapidOcr.__new__(RapidOcr)
    ocr._engine = Engine()
    assert ocr(Image.new("RGB", (4, 4))) == [] and calls == {"use_cls": False}
