from memeseeks.maintext import common_lines, is_noise, join_lines, main_text
from memeseeks.models.ocr import OcrLine


def line(text, top, height=40, score=0.99, left=10):
    """A line as OCR boxes it: as wide as its characters (a Chinese one square, a Latin one about half)."""
    cjk = sum("㐀" <= c <= "鿿" for c in text)
    right = left + height * (cjk + 0.55 * (len(text) - cjk))
    return OcrLine(text, [[left, top], [right, top], [right, top + height], [left, top + height]], score)


def test_watermarks_accounts_and_screen_furniture_are_not_the_meme():
    for text, score in [("小红书", 1.0), ("小红书号：12345678901", 1.0), ("工书号：12345678901", 0.98),   # misread too
                        ("红号：1234567890", 0.9), ("d抖音号：someone", 0.9), ("微博：某某", 0.6),
                        ("@SomeAccount", 0.99), ("Someone<someone@example.com>", 0.99), ("change.org", 0.9),
                        ("Follow", 0.99), ("divinestrike Follow", 0.98), ("TranslateTweet", 0.99), ("SHARE", 0.99),
                        ("4:25AM·Oct13,2020.TwitterforiPhone", 0.92), ("Somebody·6小時", 0.93), ("@Cyb··1天", 0.8),
                        ("BYDANIELAVERYON02/16/22", 0.99), ("Someone signed2hours ago", 0.97),
                        ("1/9", 0.99), ("109", 1.0), ("↓54", 0.79), ("1,537", 0.9), ("f", 1.0), ("in", 1.0),
                        ("DTVERAT MVUSANTLSTS", 0.5), ("+", 0.55), ("O", 0.75)]:
        assert is_noise(text, score), text
    for text, score in [("早上7:59醒来提前关掉了8:00的闹钟的我", 0.99), ("可以帮我P掉柱子吗", 1.0), ("我", 1.0),
                        ("有", 1.0), ("Life is like", 0.99), ("pls remove the pole in front of me!!", 0.98),
                        ("9693人已签下请愿书", 1.0), ("我在小红书上刷到的", 0.99), ("屠夫", 0.82)]:
        assert not is_noise(text, score), text


def test_a_line_on_many_memes_is_a_watermark_but_a_single_character_never():
    memes = [[line("某某频道", 0), line(f"第{k}张的正文", 50)] for k in range(3)] + [[line("我", 0)]] * 5
    common = common_lines(memes)
    assert "某某频道" in common and "我" not in common and not any("正文" in c for c in common)
    assert main_text(memes[0], common) == "第0张的正文"


def test_the_display_name_above_a_handle_goes_but_the_post_below_it_stays():
    lines = [line("Some Display Name", 0, 20), line("@somehandle", 22, 20), line("my cat judges me every morning", 60)]
    assert main_text(lines) == "my cat judges me every morning"


def test_wrapped_lines_are_joined_back_and_separate_captions_stay_apart():
    lines = [line("我的大脑，毫无来由地", 0, 60), line("对所有事生气", 70, 60),                 # one sentence, wrapped
             line("这人的Photoshop有装物理引", 400, 60), line("擎？", 470, 60),
             line("Life is like", 800, 50), line("a dick", 860, 50),
             line("你知道吗？", 1200, 60), line("水下的飞机比天上的潜水艇更多", 1270, 60)]    # a question ends a line
    assert join_lines(lines).split("\n") == ["我的大脑，毫无来由地对所有事生气", "这人的Photoshop有装物理引擎？",
                                             "Life is like a dick", "你知道吗？", "水下的飞机比天上的潜水艇更多"]


def test_a_meme_that_is_only_a_watermark_has_no_text():
    assert main_text([line("小红书", 0, 20), line("小红书号：12345678901", 30, 20)]) == ""


def test_more_screen_furniture_misread_watermarks_and_credits():
    for text in ["帖子", "貼文", "跟隨", "热门", "显示回复", "查看动态>", "简介", "16小时前江苏", "20,108notes",
                 "99Retweets181Likes", "20:20·2026/6/28·59萬次查看", "6萬", "Reportlt", "BestAnswer-ChosenbyAsker",
                 "小红节", "小红书具", "翻/製：SOMEONE", "译@某人", "品o"]:
        assert is_noise(text, 0.95), text
    assert not is_noise("人在什么时候最舒服", 0.99) and not is_noise("一看时间才6点", 1.0)


def test_labels_side_by_side_are_not_one_sentence_and_nothing_joins_across_a_dropped_line():
    labels = [line("天鹅肉", 0, 50, left=10), line("秤碗", 60, 50, left=600)]
    assert join_lines(labels) == "天鹅肉\n秤碗"
    name_then_post = [line("某个账号", 0, 40), line("@somebody", 0, 40, left=500), line("正文从这里开始", 45, 40)]
    assert main_text(name_then_post) == "正文从这里开始"
    bubble = [line("Ihunt aliens", 0, 40), line("我猎杀外星人", 45, 40)]
    assert join_lines(bubble) == "Ihunt aliens 我猎杀外星人"          # Latin next to Chinese keeps a space


def test_a_chinese_name_only_above_an_at_handle_and_watermark_bits_next_to_the_account_line():
    title = [line("我，就这样躺着因为知道", 0), line("我的闹钟已经要响了", 45), line("微博：@某某memes", 90, 20)]
    assert main_text(title) == "我，就这样躺着因为知道我的闹钟已经要响了"   # one wrapped sentence; a credit is no handle
    name = [line("某个账号", 0, 30), line("@somebody", 32, 20), line("正文在这里。", 80)]
    assert main_text(name) == "正文在这里。"
    mark = [line("正文在这里。", 0), line("小幼", 300, 20), line("小红书号：12345678", 322, 20)]
    assert main_text(mark) == "正文在这里。"


def test_times_dates_and_credits_written_other_ways():
    for text in ["935pm1-16Nov2018", "October", "Oct 13", "：好色龙"]:
        assert is_noise(text, 0.95), text
