"""A meme's text as it is meant to be read, written out by a vision-language model (docs/design.md, "Meme text").

What rules (maintext.py) cannot do: read the picture to put right what OCR misread, tell a dialogue from a
comment under it, leave out an original that sits next to its translation. This needs a GPU (Qwen3-VL-8B takes
about 19 GB of video memory, under a second a meme); it runs as an index stage where there is one, and a library
without it keeps the rule-based text.

Output format, one item per line:
    - 可以幫我P掉柱子嗎？              a line of a dialogue
    【评论】迷因酒吧：這人的…？         a comment or reply, with who wrote it when known
    anything else                     a title, the body, a caption
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .maintext import is_noise

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"

# Tried on the maintainer's 128 memes: this wording does best; small changes move an 8B model's answers a lot,
# so the checks it misses (a copy of the example, credits, the same line twice) are clean()'s job, not the prompt's.
PROMPT = """这是一张梗图（常见的是社交网站截图、聊天记录、带字的图）。请整理出图里值得读的文字，只输出整理结果，不要解释。

规则：
1. 按图上写的字照抄：繁体就写繁体，简体就写简体，不改写，不纠正图上本来的用字（谐音、错字梗要原样保留），不补充图里没有的内容。
2. 不要这些：平台水印（小红书、小红书号等），账号昵称和 @账号，时间日期，点赞、评论、转发的数字，按钮和界面上的字（如 Follow、关注、Report It、Resolved Question、Best Answer、简介、评论(123)、回复、显示回复），翻页的「1/9」。
3. 一句话旁边配了中文翻译时，只写中文翻译，外文原文一个词也不写（例如图上「Sure. 如你所愿」只写「如你所愿」）。没有中文翻译的外文照抄。
4. 对话（聊天记录、一问一答、角色台词）：每句话单独一行，每一句都以「- 」开头（第一句也是）；图上写了说话人的（如「撒旦：」）保留。
5. 评论和回复（帖子下面的回复、转发者或频道的点评、引用别人帖子时说的话）：单独一行，写成「【评论】名字：内容」，名字是发这条评论的人的昵称；看不出是谁就写「【评论】内容」。
6. 其他文字（标题、正文、图上配的字）：按阅读顺序，一句话或一段话一行。
7. 每句话只写一次：写成了【评论】的内容，不要再写成对话或正文。

格式示例（与这张图无关；图上是两句中英对照的聊天，下面是一个频道的点评）：
- 你今天吃了吗？
- 吃了。
【评论】某某频道：这也能聊起来？"""

COMMENT = "【评论】"
_EXAMPLE = ("某某频道", "你今天吃了吗")  # the prompt's example: never a meme's text
_NOTHING = {"无", "无。", "（无）", "(无)", "没有文字", "无文字"}
_NAME = re.compile(r"^([^：:]{1,24})[：:]\s*(.+)$")


def _parts(line: str) -> tuple[str, str, str]:
    """(kind, name, words) of one output line: kind is "comment", "dialogue" or "text"."""
    if line.startswith(COMMENT):
        rest = line[len(COMMENT):].strip()
        m = _NAME.match(rest)
        return ("comment", m.group(1).strip(), m.group(2).strip()) if m else ("comment", "", rest)
    if line.startswith("- ") or line == "-":
        return "dialogue", "", line[1:].strip().removeprefix("- ").strip()  # "- - Kant": one dash is enough
    return "text", "", line


def clean(raw: str) -> str:
    """The model's answer, checked: no copy of the prompt's example, no watermark or credit it let through (the
    same rules as maintext.py), nothing twice (a reply written as a line of dialogue and as a comment)."""
    text = raw.strip().strip("`").strip()
    if not text or text in _NOTHING or any(mark in text for mark in _EXAMPLE):
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    said = {_parts(line)[2] for line in lines if line.startswith(COMMENT)}
    out: list[str] = []
    for line in lines:
        kind, name, words = _parts(line)
        if not words or words in _NOTHING or is_noise(words, 1.0):
            continue                                   # 【评论】某人：无 — the model's "nothing" leaking into a line
        if kind == "dialogue":
            line = f"- {words}"
        if kind == "comment" and name and is_noise(f"{name}：{words}", 1.0):
            continue                                   # 【评论】小红书：42245681147
        if kind != "comment" and words in said:
            continue                                   # the same reply again, as a line of dialogue
        if line not in out:
            out.append(line)
    return "\n".join(out)


class Tidier:
    def __init__(self, model_id: str = MODEL_ID):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self._torch = torch
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16, device_map="cuda").eval()

    def __call__(self, image) -> str:
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": PROMPT}]}]
        inputs = self.processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                    return_dict=True, return_tensors="pt").to(self.model.device)
        with self._torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=600, do_sample=False)
        raw = self.processor.batch_decode(ids[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        return clean(raw)


def main(argv=None) -> int:
    """python -m memeseeks.tidy <folder> <out.jsonl>: tidy every image in a folder (named <id>.<ext>), one JSON
    line per image, skipping ids already in out.jsonl. For a library whose own computer has no GPU: run this on
    one that has (tools/tidy_remote.py), then bring the lines back into the library's index/tidy.jsonl."""
    import json

    from .images import load_image

    folder, out = Path((argv or sys.argv[1:])[0]), Path((argv or sys.argv[1:])[1])
    done = set()
    if out.exists():
        done = {json.loads(line)["id"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = sorted(p for p in folder.iterdir() if p.stem not in done and p.suffix.lower() in
                  (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"))
    tidier = Tidier()
    with out.open("a", encoding="utf-8") as f:
        for k, path in enumerate(todo, 1):
            try:
                value = tidier(load_image(str(path)))
            except Exception as exc:  # one bad image must not stop the rest
                value = {"_error": f"{type(exc).__name__}: {exc}"}
            f.write(json.dumps({"id": path.stem, "relpath": path.name, "value": value}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"tidy: {k}/{len(todo)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
