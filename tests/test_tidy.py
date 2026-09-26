from memeseeks.tidy import clean


def test_the_models_answer_is_kept_when_it_is_right():
    raw = "- 可以帮我P掉柱子吗？\n- 如你所愿\n【评论】某个酒吧：这人的Photoshop有装物理引擎？"
    assert clean(raw) == raw
    assert clean("我的生活正在分崩离析\n但幸好我的袜子很酷\n") == "我的生活正在分崩离析\n但幸好我的袜子很酷"


def test_no_text_and_a_copy_of_the_prompts_example_are_no_text():
    assert clean("无") == "" and clean("  ") == "" and clean("```\n无\n```") == ""
    assert clean("- 你今天吃了吗？\n- 吃了。\n【评论】某某频道：这也能聊起来？") == ""


def test_a_reply_written_twice_is_kept_once_as_the_comment():
    raw = "为什么车上有一只浣熊\n- 管好你自己\n【评论】吃花生酱的浣熊：管好你自己"
    assert clean(raw) == "为什么车上有一只浣熊\n【评论】吃花生酱的浣熊：管好你自己"


def test_watermarks_credits_and_times_the_model_let_through_are_dropped():
    raw = ("飲酒智慧王：雙手各拿一杯酒\n譯：某某\nphoto by someone\nBY SOMEONE ON 02/16/22\nSomeone · 6小時\n"
           "【评论】小红书：12345678901\n- @somebody")
    assert clean(raw) == "飲酒智慧王：雙手各拿一杯酒"


def test_the_same_line_twice_is_written_once():
    assert clean("FLOOR 4. DO NOT REMOVE\n4楼物品，请勿带走\nFLOOR 4. DO NOT REMOVE") == \
        "FLOOR 4. DO NOT REMOVE\n4楼物品，请勿带走"


def test_the_meme_page_shows_the_tidied_text_and_search_keeps_the_rules(tmp_path):
    import json

    from memeseeks.index import display_texts, load_index, route_texts

    box = [[0, 0], [200, 0], [200, 40], [0, 40]]
    ocr = {"a": [{"text": "可以我P掉柱子", "box": box, "score": 1.0}],
           "b": [{"text": "我的生活正在分崩离析", "box": box, "score": 1.0}],
           "c": [{"text": "第三张", "box": box, "score": 1.0}]}
    tidy = {"a": "- 可以帮我P掉柱子吗？\n- 如你所愿", "b": {"_error": "CUDA out of memory"}, "c": ""}
    (tmp_path / "ocr.jsonl").write_text("\n".join(json.dumps({"id": i, "value": v}, ensure_ascii=False)
                                                  for i, v in ocr.items()), encoding="utf-8")
    (tmp_path / "tidy.jsonl").write_text("\n".join(json.dumps({"id": i, "value": v}, ensure_ascii=False)
                                                   for i, v in tidy.items()), encoding="utf-8")
    idx = load_index(tmp_path)
    shown = display_texts(idx)
    assert shown["a"] == "- 可以帮我P掉柱子吗？\n- 如你所愿"          # the model's text, on the meme page
    assert shown["b"] == "我的生活正在分崩离析" and shown["c"] == "第三张"  # it failed, or found nothing: the rules
    assert route_texts(idx)["ocr"]["a"] == "可以我P掉柱子"               # search keeps the rules' text


def test_a_nothing_inside_a_line_and_a_double_dash_are_put_right():
    assert clean("- 我不喜欢这个\n无\n【评论】某人：无") == "- 我不喜欢这个"
    assert clean("- \"To do is to be.\"\n- - Kant") == "- \"To do is to be.\"\n- Kant"


def test_notes_keep_only_what_was_asked_in_the_shape_asked():
    from memeseeks.tidy import clean_notes

    got = clean_notes('好的：{"类型": "梗图", "梗": "电车难题", "画面": "一个人拉着拉杆", "情绪": ["调侃", 3],'
                      ' "翻译": null, "说话人": "我", "多余": 1}')
    assert got == {"类型": "梗图", "梗": "电车难题", "画面": "一个人拉着拉杆", "情绪": ["调侃", "3"], "翻译": "",
                   "说话人": []}
    assert clean_notes("not json")["类型"] == "" and clean_notes('{"类型": "壁纸"}')["类型"] == ""
    assert clean_notes('{"梗": "猫猫表情包"}')["梗"] == ""  # a kind of image, not a meme's name


def test_a_translation_belongs_only_under_text_that_is_mostly_not_chinese():
    from memeseeks.tidy import wants_translation

    assert wants_translation("Thanks, mailman.") and wants_translation("いつもありがとう")
    assert not wants_translation("每个人的身体里都有两只狼") and not wants_translation("")
    assert not wants_translation("没有人有危险 nobody")  # the Chinese is there already


def test_the_memes_name_is_searchable_and_shown_apart_from_its_text(tmp_path):
    import json

    from memeseeks.index import display_texts, load_index, route_texts

    box = [[0, 0], [200, 0], [200, 40], [0, 40]]
    (tmp_path / "ocr.jsonl").write_text(json.dumps({"id": "a", "value": [{"text": "没有人有危险", "box": box, "score": 1.0}]},
                                                   ensure_ascii=False), encoding="utf-8")
    (tmp_path / "notes.jsonl").write_text(json.dumps({"id": "a", "value": {"梗": "电车难题", "翻译": ""}}, ensure_ascii=False),
                                          encoding="utf-8")
    idx = load_index(tmp_path)
    assert route_texts(idx)["ocr"]["a"] == "没有人有危险\n电车难题" and display_texts(idx)["a"] == "没有人有危险"
