from PIL import Image

from memeseeks.masking import mask_text


def test_mask_fills_box_with_median_and_leaves_rest():
    im = Image.new("RGB", (20, 20), (10, 10, 10))
    for x in range(5, 10):
        for y in range(5, 10):
            im.putpixel((x, y), (250, 250, 250))
    out = mask_text(im, [[[5, 5], [9, 5], [9, 9], [5, 9]]], pad=0)
    assert out.getpixel((7, 7)) == (10, 10, 10)
    assert out.getpixel((0, 0)) == (10, 10, 10)
    assert im.getpixel((7, 7)) == (250, 250, 250)  # input untouched
