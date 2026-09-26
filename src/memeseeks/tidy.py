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

# A second question, asked separately so the text above stays as it is: what else the model can tell about a meme.
# Checked on the maintainer's collection (experiments/results/explore.md): the meme's name and a translation are
# used; the rest is kept for later.
NOTES_PROMPT = """请看这张图，只输出一个 JSON 对象，不要输出其他任何内容。字段：
"类型"：从这三个里选一个——
  "梗图"：单独拿出来看就好笑或有意思的图（段子、帖子截图、聊天截图、配文图、漫画），重点在图要讲的内容；
  "表情包"：聊天时发给别人、用来表达情绪或回应对方的图（通常是一个人物或动物的表情或动作，配几个字或不配字）；
  "其他"：普通照片、广告、没有笑点的截图等。
"梗"：如果这是某个知名的梗或模板（例如“电车难题”“每个人身体里都有两只狼”“Pop猫”“Drake 不要/要”），写出它的名字，否则写空字符串。
"画面"：一句话描述画面里有什么（人物、动物、场景、动作、表情），不超过 30 个字。
"情绪"：这张图表达的情绪或态度，1 到 3 个词组成的数组（例如 无语、破防、开心、阴阳怪气、摆烂）。
"翻译"：如果图里的主要文字是外文、而且图里没有中文翻译，把它翻成通顺的中文；否则写空字符串。
"说话人"：如果图里是聊天记录或对话，按出现顺序列出说话的双方（例如 ["我", "对方"] 或 ["撒旦", "我"]），否则写空数组。"""

_NOTE_FIELDS = {"类型": str, "梗": str, "画面": str, "情绪": list, "翻译": str, "说话人": list}


def clean_notes(raw: str) -> dict:
    """The model's JSON, with only the fields asked for, each of the type asked for."""
    from .models.vlm import parse_json_object

    found = parse_json_object(raw)
    out = {}
    for key, kind in _NOTE_FIELDS.items():
        value = found.get(key)
        if kind is str:
            out[key] = value.strip() if isinstance(value, str) else ""
        else:
            out[key] = [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []
    if out["类型"] not in ("梗图", "表情包", "其他"):
        out["类型"] = ""
    out["梗"] = meme_name(out)
    return out


def meme_name(note) -> str:
    """The meme's name from its notes: none when the model named a kind of image rather than a meme (猫猫表情包)."""
    name = note.get("梗") if isinstance(note, dict) else None
    if not isinstance(name, str) or re.search(r"(表情包|表情|梗图)$", name.strip()):
        return ""
    return name.strip()


def wants_translation(text: str) -> bool:
    """Whether a translation belongs under this text: it has one, and it is mostly not Chinese."""
    letters = [c for c in text if c.isalpha()]
    han = sum(1 for c in letters if 0x4E00 <= ord(c) <= 0x9FFF)
    return bool(letters) and han * 2 < len(letters)


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

    def _ask(self, image, prompt: str, max_new_tokens: int) -> str:
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
        inputs = self.processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                    return_dict=True, return_tensors="pt").to(self.model.device)
        with self._torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return self.processor.batch_decode(ids[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]

    def __call__(self, image) -> str:
        return clean(self._ask(image, PROMPT, 600))

    def notes(self, image) -> dict:
        return clean_notes(self._ask(image, NOTES_PROMPT, 300))


def main(argv=None) -> int:
    """python -m memeseeks.tidy <folder> <out.jsonl>: tidy every image in a folder (named <id>.<ext>), one JSON
    line per image ({"id", "value": the text, "notes": {...}}), skipping ids already in out.jsonl. For a library
    whose own computer has no GPU: run this on one that has (remote.py), and bring the lines back."""
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
                image = load_image(str(path))
                value, notes = tidier(image), tidier.notes(image)
            except Exception as exc:  # one bad image must not stop the rest
                value = notes = {"_error": f"{type(exc).__name__}: {exc}"}
            f.write(json.dumps({"id": path.stem, "relpath": path.name, "value": value, "notes": notes},
                               ensure_ascii=False) + "\n")
            f.flush()
            print(f"tidy: {k}/{len(todo)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
