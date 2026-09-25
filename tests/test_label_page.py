import json
import re

from tools.make_label_page import render_page


def test_page_embeds_all_images_and_escapes_script_breakers():
    html = render_page(["子目录/无语 猫.jpg", "a</script>.png"], "my-memes", [["无语", "子目录/无语 猫.jpg"]])
    payload = json.loads(re.search(r"const DATA = (.*?);\n", html).group(1))
    assert payload["images"] == ["子目录/无语 猫.jpg", "a</script>.png"]
    assert payload["rows"] == [["无语", "子目录/无语 猫.jpg"]]
    assert payload["base"] == "my-memes"
    assert "a</script>.png" not in html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
