#!/usr/bin/env python3
"""生成 InsureAI 的社交分享图（Open Graph / Twitter Card）。

输出: og-image.png (1200x630)
设计: 与 logo 同色系（#F97316 橙 → #EF4444 红对角渐变）+ 六边形网络标记 + 品牌文案。
零外部依赖（仅 Pillow + numpy）。中文字体回退到 macOS 系统字体。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630

# 品牌渐变锚点（与 logo.svg 一致：左上 #F97316 → 右下 #EF4444）
C_TOPLEFT = np.array([0xF9, 0x73, 0x16])
C_BOTRIGHT = np.array([0xEF, 0x44, 0x44])

FONT_DIR = "/System/Library/Fonts"
# 拉丁字体（Helvetica 粗）回退链
LATIN_FONTS = [
    f"{FONT_DIR}/Helvetica.ttc",
    f"{FONT_DIR}/HelveticaNeue.ttc",
    f"{FONT_DIR}/ArialHB.ttc",
]
# 中文字体回退链
CJK_FONTS = [
    f"{FONT_DIR}/PingFang.ttc",
    f"{FONT_DIR}/Hiragino Sans GB.ttc",
    f"{FONT_DIR}/STHeiti Medium.ttc",
    f"{FONT_DIR}/STHeiti Light.ttc",
]


def _load_font(paths, size, idx=0):
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size, index=idx)
            except Exception:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
    return ImageFont.load_default()


def build_gradient():
    xs = np.linspace(0, 1, W)
    ys = np.linspace(0, 1, H)
    gx, gy = np.meshgrid(xs, ys)
    t = (gx + gy) / 2.0  # 对角：左上 0 → 右下 1
    arr = (C_TOPLEFT * (1 - t[..., None]) + C_BOTRIGHT * t[..., None]).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def draw_hex_cluster(draw, cx, cy, scale):
    """在 (cx,cy) 以 scale 比例绘制六边形网络（复刻 logo 视觉）。"""
    # 中心六边形（加粗，白）
    def hex_points(cx, cy, r, rot=0.0):
        pts = []
        for i in range(6):
            a = np.radians(60 * i + 30 + rot)
            pts.append((cx + r * np.cos(a), cy + r * np.sin(a)))
        return [(float(x), float(y)) for x, y in pts]

    # 中心六边形
    draw.line(hex_points(cx, cy, 150 * scale), fill=(255, 255, 255), width=int(6 * scale), joint="curve")
    # 三个环绕六边形（低透明度）
    for off, op in [((0, -165 * scale), 70), ((143 * scale, 82 * scale), 70), ((-143 * scale, 82 * scale), 70)]:
        draw.line(hex_points(cx + off[0], cy + off[1], 95 * scale), fill=(255, 255, 255), width=int(3 * scale), joint="curve")
    # 中心核心三角
    tri = [(cx, cy - 55 * scale), (cx + 48 * scale, cy + 38 * scale), (cx - 48 * scale, cy + 38 * scale)]
    draw.polygon(tri, fill=(255, 255, 255))
    # 顶点圆点
    for px, py in hex_points(cx, cy, 150 * scale):
        draw.ellipse([px - 6 * scale, py - 6 * scale, px + 6 * scale, py + 6 * scale], fill=(255, 255, 255))


def main(out_path):
    img = build_gradient()
    draw = ImageDraw.Draw(img, "RGBA")

    # 左侧文字区暗化叠层（提升对比）
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.polygon([(0, 0), (int(W * 0.62), 0), (int(W * 0.42), H), (0, H)], fill=(10, 8, 8, 120))
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 右侧六边形网络
    draw_hex_cluster(draw, 915, 315, 1.0)

    # 文案（左侧）
    latin = _load_font(LATIN_FONTS, 132)
    cjk = _load_font(CJK_FONTS, 52)
    cjk_small = _load_font(CJK_FONTS, 34)

    draw.text((96, 196), "InsureAI", font=latin, fill=(255, 255, 255))
    draw.text((100, 332), "保险行业动态资讯聚合", font=cjk, fill=(255, 240, 235))
    # 分隔线
    draw.line([(102, 410), (560, 410)], fill=(255, 255, 255), width=3)
    draw.text((100, 432), "每日精选 · AI 评分 · 权威研究报告", font=cjk_small, fill=(255, 224, 216))

    img.save(out_path, "PNG", optimize=True)
    print(f"wrote {out_path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "og-image.png"
    main(out)
