"""Render exact, post-specific information cards without copied product artwork."""
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image, ImageDraw, ImageFont

FONT_PATHS = [os.environ.get('TORECA_FONT', ''), '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']


def font(size):
    for path in FONT_PATHS:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size, index=0)
    raise RuntimeError('Japanese font missing; refusing an unreadable image')


def lines(draw, text, face, width):
    result, line = [], ''
    for char in text:
        if char == '\n' or draw.textlength(line + char, font=face) > width:
            result.append(line)
            line = '' if char == '\n' else char
        else:
            line += char
    if line:
        result.append(line)
    return result


def fit(draw, text, width, height, start=58, minimum=24):
    for size in range(start, minimum - 1, -1):
        face = font(size)
        wrapped = lines(draw, text, face, width)
        if len(wrapped) * (size + 15) <= height:
            return face, wrapped, size + 15
    raise ValueError('Text does not fit; refusing to crop factual content')


def render_card(item, label, now, destination):
    image = Image.new('RGB', (1200, 1200), '#fff8fc')
    draw = ImageDraw.Draw(image)
    kind = item.get('kind', 'news')
    accent = '#b5447c' if kind == 'guide' else '#4d58a1'
    # A restrained card motif; all headline and detail content changes per post.
    draw.rounded_rectangle((34, 34, 1166, 1166), radius=36, fill='white', outline='#efd9e5', width=3)
    draw.rounded_rectangle((65, 66, 1135, 144), radius=24, fill=accent)
    category = {'guide': '保存用ミニガイド', 'spotlight': '公式商品情報の紹介', 'news': '公式の新着告知'}[kind]
    draw.text((92, 80), 'トレカ女子ちゃん  /  ' + category, font=font(31), fill='white')
    draw.text((80, 178), label, font=font(28), fill=accent)
    face, title_lines, step = fit(draw, item['title'], 1030, 305)
    y = 235
    for line in title_lines:
        draw.text((80, y), line, font=face, fill='#26243a')
        y += step
    if kind == 'guide':
        details = item['bullets']
    else:
        details = ['発表日：' + item['published'],
                   '店舗：' + item['store'] if item.get('store') else '出典：' + label,
                   '紹介記事です。現在の受付・在庫は公式へ' if kind == 'spotlight' else '受付状況・応募条件は公式ページで確認']
    y = 590
    for index, detail in enumerate(details[:3], 1):
        draw.rounded_rectangle((74, y, 1126, y + 116), radius=20, fill='#f8f1f6')
        draw.ellipse((94, y + 28, 146, y + 80), fill=accent)
        draw.text((110, y + 30), str(index), font=font(27), fill='white')
        face, wrapped, step = fit(draw, detail, 905, 94, start=32)
        ty = y + (116 - len(wrapped) * step) // 2 - 2
        for line in wrapped:
            draw.text((170, ty), line, font=face, fill='#363246')
            ty += step
        y += 136
    domain = urlsplit(item['url']).hostname
    draw.text((80, 1024), '参照：' + domain, font=font(25), fill='#665b6c')
    draw.text((80, 1067), '作成 ' + now.strftime('%Y/%m/%d %H:%M') + ' JST  |  詳細リンクは投稿本文へ', font=font(23), fill='#665b6c')
    draw.text((80, 1110), '非公式の情報アカウント / 要点は編集部による整理', font=font(22), fill='#847487')
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path


def image_name(item):
    return hashlib.sha256((item['key'] + '\n' + item['title']).encode()).hexdigest()[:24] + '.png'
