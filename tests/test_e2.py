from experiments.e2_crosslingual.pairs import caption_text, pick_captions


def _e(boxes, votes, url):
    return {"boxes": boxes, "url": url, "metadata": {"img-votes": votes}}


def test_pick_captions_filters_and_orders_by_votes():
    entries = [
        _e(["TOP TEXT", "BOTTOM TEXT HERE"], "1,204", "u1"),
        _e(["ONLY ONE BOX"], "9,000", "u2"),                      # 1 box -> out
        _e(["", "EMPTY TOP"], "500", "u3"),                       # empty box -> out
        _e(["SEE", "https://x.com"], "800", "u4"),                # url -> out
        _e(["多语言", "不是英文的说明文字"], "700", "u5"),          # non-English -> out
        _e(["SECOND BEST", "STILL A GOOD MEME"], "33", "u6"),
    ]
    assert [e["url"] for e in pick_captions(entries, n=3)] == ["u1", "u6"]
    assert caption_text(entries[0]) == "TOP TEXT / BOTTOM TEXT HERE"


def test_read_popular_accepts_cp1252_bytes():
    from experiments.e2_crosslingual.pairs import read_popular
    raw = '"ID","Name","Alternate Names"\r\n"1","Aint Nobody Got Time","ain\x92t"\r\n'.encode("latin-1")
    rows = read_popular(raw)
    assert rows[0]["Name"] == "Aint Nobody Got Time" and rows[0]["Alternate Names"] == "ain’t"


def test_read_popular_still_reads_utf8():
    from experiments.e2_crosslingual.pairs import read_popular
    assert read_popular('"ID","Name"\n"1","Doge ’"\n'.encode("utf-8"))[0]["Name"] == "Doge ’"
