from PIL import Image
import pytest

from memeseeks.images import UnreadableImage, load_image, scan_folder


def _save(img, path, **kw):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, **kw)
    return path


def test_rgba_png_composited_on_white(tmp_path):
    p = _save(Image.new("RGBA", (4, 4), (255, 0, 0, 0)), tmp_path / "t.png")
    im = load_image(p)
    assert im.mode == "RGB" and im.getpixel((0, 0)) == (255, 255, 255)


def test_palette_and_grayscale_become_rgb(tmp_path):
    for mode in ("P", "L"):
        p = _save(Image.new(mode, (4, 4)), tmp_path / f"{mode}.png")
        assert load_image(p).mode == "RGB"


def test_animated_gif_uses_first_frame(tmp_path):
    frames = [Image.new("RGB", (4, 4), c) for c in [(255, 0, 0), (0, 0, 255)]]
    p = tmp_path / "a.gif"
    frames[0].save(p, save_all=True, append_images=frames[1:])
    r, _, b = load_image(p).getpixel((0, 0))
    assert r > 200 and b < 50


def test_exif_rotation_applied(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise on display
    p = _save(Image.new("RGB", (4, 2)), tmp_path / "r.jpg", exif=exif)
    assert load_image(p).size == (2, 4)


def test_heic_loads(tmp_path):
    p = _save(Image.new("RGB", (16, 16), (0, 255, 0)), tmp_path / "phone.heic", format="HEIF")
    assert load_image(p).mode == "RGB"


def test_corrupt_file_raises(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"\xff\xd8\xff not really a jpeg")
    with pytest.raises(UnreadableImage):
        load_image(p)


def test_scan_chinese_names_duplicates_and_junk(tmp_path):
    a = _save(Image.new("RGB", (4, 4), (1, 2, 3)), tmp_path / "子目录" / "无语猫猫.png")
    (tmp_path / "副本.png").write_bytes(a.read_bytes())
    (tmp_path / "坏图.jpg").write_bytes(b"garbage")
    (tmp_path / "desktop.ini").write_text("x")
    res = scan_folder(tmp_path)
    assert len(res.records) == 1
    kept = res.records[0].relpath
    assert {kept, *res.duplicates[kept]} == {"子目录/无语猫猫.png", "副本.png"}
    assert res.unreadable == ["坏图.jpg"]
    assert res.skipped == ["desktop.ini"]
    assert len(res.records[0].id) == 16
