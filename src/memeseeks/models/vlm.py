"""Qwen2.5-VL for meme descriptions (and text-only prompts in E2/E3)."""

from __future__ import annotations

import json

from PIL import Image

DESCRIBE_PROMPT = (
    "你在整理一个梗图收藏库（以文字为主的搞笑图、截图和 meme）。请看这张图，只输出一个 JSON 对象，不要输出其他任何内容。字段：\n"
    '"画面"：一句话描述画面里有什么（人物、动物、场景、动作、表情）；\n'
    '"文字"：图中出现的文字，原样照抄，没有就写空字符串；\n'
    '"主题"：这张图在讲什么话题，2 到 4 个短词组成的数组（例如：熬夜、上班、恋爱、考试）；\n'
    '"笑点"：一句话说清这张图好笑在哪里，或它表达的观点；\n'
    '"情绪"：这张图传达的情绪或态度，2 到 5 个词；\n'
    '"梗"：如果认出这是某个知名的梗或模板，写出它的名字（中英文均可），否则写空字符串。'
)

_FIELDS = ["画面", "文字", "主题", "笑点", "情绪", "梗"]


def parse_json_object(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(raw[start:end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return {"_raw": raw}


def description_text(desc: dict) -> str:
    if "_raw" in desc:
        return str(desc["_raw"])
    parts = []
    for key in _FIELDS:
        value = desc.get(key)
        if isinstance(value, list):
            value = "；".join(str(v) for v in value if str(v).strip())
        if value and str(value).strip():
            parts.append(f"{key}：{str(value).strip()}")
    return " ".join(parts)


class QwenVl:
    def __init__(self, model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct", max_pixels: int = 1024 * 28 * 28):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        self._torch = torch
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda").eval()
        self.processor = AutoProcessor.from_pretrained(model_id, max_pixels=max_pixels)

    def chat(self, prompt: str, image: Image.Image | None = None, max_new_tokens: int = 512) -> str:
        content = ([{"type": "image"}] if image is not None else []) + [{"type": "text", "text": prompt}]
        text = self.processor.apply_chat_template([{"role": "user", "content": content}],
                                                  tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[image] if image is not None else None,
                                return_tensors="pt").to(self.model.device)
        with self._torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return self.processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()

    def describe(self, image: Image.Image) -> dict:
        return parse_json_object(self.chat(DESCRIBE_PROMPT, image))
