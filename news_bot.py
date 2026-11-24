"""Official-news watcher. Durable send intents prevent blind duplicate retries."""
import argparse
from datetime import datetime, timedelta, timezone, date
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

JST = timezone(timedelta(hours=9))
AGENT = 'TorecaNewsBot/0.1 (+https://github.com/ncb1310/toreca-news-bot)'
ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'data/state.json'
SOURCES = {
    'pokemon': ('ポケカ', 'https://www.pokemon-card.com/info/'),
    'onepiece': ('ワンピカード', 'https://www.onepiece-cardgame.com/topics/'),
    'labo': ('カードラボ', 'https://www.c-labo.jp/blog/'),
    'hobby': ('ホビステ', 'https://www.hbst.net/'),
    'kids': ('イオン', 'https://www.kidsrepublic.jp/campaign/'),
    'pcstore': ('ポケセン通販', 'https://www.pokemoncenter-online.com/?main_page=lottery'),
    'furu': ('古本市場', 'https://www.furu1.net/news/'),
}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def has_class(self, name):
        return name in self.attrs.get('class', '').split()

    def walk(self):
        yield self
        for item in self.children:
            if isinstance(item, Node):
                yield from item.walk()

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)


class DOM(HTMLParser):
    VOID = set('area base br col embed hr img input link meta param source track wbr'.split())

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def canonical_url(base, href):
    url = urlsplit(urljoin(base, href))
    # Restrict outgoing news links to the two confirmed manufacturer domains.
    if url.scheme != 'https' or url.hostname != urlsplit(base).hostname or url.username:
        return None
    return urlunsplit((url.scheme, url.netloc, url.path, url.query, ''))


def parse(source, html):
    root = DOM(html).root
    nodes = list(root.walk())
    if source not in ('pokemon', 'onepiece'):
        return parse_retailer(source, nodes)
    if source == 'pokemon':
        container = next((n for n in nodes if n.attrs.get('id') == 'newsTab_all'), None)
        if container is None:
            raise ValueError('pokemon news container changed')
        cards = [n for n in container.walk() if n.tag == 'a' and n.has_class('List_item_inner')]
    else:
        cards = [n for n in nodes if n.tag == 'li' and n.has_class('topicDetail')]
    items = {}
    for card in cards:
        descendants = list(card.walk())
        date_node = next((n for n in descendants if n.has_class('Date') or n.has_class('topicDate')), None)
        if date_node is None:
            continue
        match = re.fullmatch(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', clean(date_node.text()))
        if not match:
            continue
        try:
            published = date(*map(int, match.groups())).isoformat()
        except ValueError:
            continue
        if source == 'pokemon':
            image = next((n for n in descendants if n.tag == 'img' and n.attrs.get('alt')), None)
            body = next((n for n in descendants if n.has_class('List_body')), None)
            title = image.attrs['alt'] if image else (body.text() if body else '')
            category = next((clean(n.text()) for n in descendants if n.has_class('Calendar_Label')), '')
            link = card
        else:
            title_node = next((n for n in descendants if n.has_class('js_topicTit')), None)
            title = title_node.text() if title_node else ''
            category = next((clean(n.text()) for n in descendants if n.has_class('topicCategory')), '')
            link = next((n for n in descendants if n.tag == 'a' and n.attrs.get('href')), None)
        title = clean(title)
        url = canonical_url(SOURCES[source][1], link.attrs.get('href', '')) if link else None
        if not title or not url:
            continue
        # Same URL may receive new announcements; title and publication date matter.
        key = hashlib.sha256((url + '\n' + published + '\n' + title).encode()).hexdigest()
        items[key] = {'key': key, 'source': source, 'title': title,
                      'url': url, 'published': published, 'category': category}
    if not items:
        raise ValueError('No valid news items; refusing to reset baseline')
    return list(items.values())


def parse_retailer(source, nodes):
    def first_class(node, class_name):
        return next((n for n in node.walk() if n.has_class(class_name)), None)

    def text_of(node):
        return clean(node.text()) if node else ''

    items = {}
    for node in nodes:
        title = published = href = store = game = ''
        closed = False
        if source == 'labo' and node.has_class('claboCard'):
            title_node = first_class(node, 'claboCard_title')
            link = next((n for n in title_node.walk() if n.tag == 'a'), None) if title_node else None
            title = text_of(title_node)
            published = text_of(first_class(node, 'claboCard_date'))
            store = text_of(first_class(node, 'claboCard_shop'))
            game = text_of(first_class(node, 'claboCard_tags'))
            href = link.attrs.get('href', '') if link else ''
        elif source == 'hobby' and node.attrs.get('id') == 'news':
            for link in node.walk():
                if link.tag != 'a':
                    continue
                header = next((n for n in link.walk() if n.tag == 'h4'), None)
                if not header:
                    continue
                value = text_of(header)
                match = re.match(r'【(\d{4}\.\d{1,2}\.\d{1,2})】(.*)', value)
                if match:
                    record_retail(items, source, match[2], match[1], link.attrs.get('href', ''), '', '')
            continue
        elif source == 'kids' and node.tag == 'a' and '/campaign/campaign_detail/' in node.attrs.get('href', ''):
            image = next((n for n in node.walk() if n.tag == 'img' and n.attrs.get('alt')), None)
            title = image.attrs['alt'] if image else ''
            value = text_of(node)
            match = re.search(r'\d{4}\.\d{1,2}\.\d{1,2}', value)
            published = match[0] if match else ''
            closed = '終了しました' in value
            href = node.attrs['href']
        elif source == 'pcstore' and node.tag == 'a' and node.attrs.get('href', '').startswith('/news/?id='):
            title = text_of(first_class(node, 'ttl'))
            published = text_of(first_class(node, 'time')).replace('年', '.').replace('月', '.').replace('日', '')
            href = node.attrs['href']
        elif source == 'furu' and node.tag == 'a' and node.has_class('news__body__content__list__link'):
            title_node = first_class(node, 'news__body__content__list__link__title')
            if title_node:
                # Ignore the presentation-only NEW badge.
                title = clean(''.join(c if isinstance(c, str) else '' for c in title_node.children))
            published = text_of(first_class(node, 'news__body__content__list__link__date'))
            href = node.attrs.get('href', '')
        if title and published and href:
            record_retail(items, source, title, published, href, store, game, closed)
    if not items:
        raise ValueError('Retailer news layout changed or no dated announcements')
    return list(items.values())


def record_retail(items, source, title, published, href, store, game, closed=False):
    match = re.fullmatch(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', published)
    url = canonical_url(SOURCES[source][1], href)
    if not match or not url:
        return
    try:
        published = date(*map(int, match.groups())).isoformat()
    except ValueError:
        return
    key = hashlib.sha256((url + '\n' + published + '\n' + title).encode()).hexdigest()
    items[key] = {'key': key, 'source': source, 'title': title, 'published': published,
                  'url': url, 'category': game, 'store': store,
                  'closed': closed or bool(re.search(r'応募は終了|受付終了|販売終了|抽選終了', title))}


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': AGENT}), timeout=25) as response:
        if urlsplit(response.url).hostname != urlsplit(url).hostname:
            raise ValueError('Unexpected redirect host')
        return response.read(3_000_001).decode('utf-8-sig')


def official_page(url):
    origin = urlsplit(url)
    robots = urlunsplit((origin.scheme, origin.netloc, '/robots.txt', '', ''))
    try:
        body = fetch(robots)
    except HTTPError as exc:
        if exc.code not in (404, 410):
            raise
    else:
        rules = RobotFileParser()
        rules.parse(body.splitlines())
        if not rules.can_fetch(AGENT, url):
            raise ValueError('robots.txt disallows this source')
    return fetch(url)


def eligible(item, now):
    age = (now.astimezone(JST).date() - date.fromisoformat(item['published'])).days
    if not 0 <= age <= 1:
        return False
    title = item['title']
    if item.get('closed'):
        return False
    if item['source'] not in ('pokemon', 'onepiece'):
        if not re.search(r'ポケモンカード|ポケカ|ONE\s*PIECE|ワンピースカード|ワンピカード', title + item.get('category', ''), re.I):
            return False
        if not re.search(r'予約|抽選|再販|再入荷|販売|発売', title):
            return False
    if age and re.search(r'本日|今日|まもなく|明日|今夜', title):
        return False
    # Product announcements or explicit sales news; event lotteries are excluded.
    if re.search(r'大会|チャンピオン|エントリー|資格試験|参加規約|ライブ配信', title):
        return False
    return item['category'] in ('商品', 'PRODUCTS') or bool(re.search(r'予約|抽選|再販|再入荷|販売|発売', title))


def post_hashtags(item):
    """Relevant tags are mandatory for every automated post, including guides."""
    content = ' '.join(str(item.get(field, '')) for field in ('title', 'body', 'category'))
    tags = ['#トレカ']
    if item.get('source') in ('pokemon', 'pcstore') or re.search(r'ポケカ|ポケモンカード', content):
        tags.append('#ポケカ')
    if item.get('source') == 'onepiece' or re.search(r'ワンピ|ONE\\s*PIECE', content, re.I):
        tags.append('#ワンピースカード')
    if item.get('kind') == 'guide':
        tags.append('#トレカ初心者')
    elif re.search(r'抽選', item.get('title', '')):
        tags.append('#抽選情報')
    elif re.search(r'予約', item.get('title', '')):
        tags.append('#予約情報')
    elif re.search(r'再販|再入荷', item.get('title', '')):
        tags.append('#再販情報')
    return ' '.join(tags[:3])


def lottery_details(item, html, now):
    root = DOM(html).root
    scope = next((n for n in root.walk() if n.tag == 'article'), None)
    if scope is None:
        scope = next((n for n in root.walk() if n.tag == 'main'), root)
    nodes = list(scope.walk())
    fields = {clean(n.text()) for n in nodes if n.tag in ('p', 'li', 'div', 'dd', 'tr')
              and len(n.text()) <= 180}
    day = r'(?:(\d{4})[年/])?(\d{1,2})[月/](\d{1,2})日?(?:[（(][月火水木金土日](?:曜)?[）)])?'
    deadlines = set()
    for field in fields:
        if not re.search(r'(?:応募|受付|抽選)(?:期間|期限|締切|締め切り|終了)', field):
            continue
        match = re.search(r'(?:締切[り]?|締め切り|期限|終了|[～〜~])[\s：:]*' + day
                          + r'(?:\s*(\d{1,2})[:：](\d{2}))?', field)
        if match:
            year, month, d, hour, minute = match.groups()
            try:
                deadline = datetime(int(year or item['published'][:4]), int(month), int(d),
                                    int(hour or 23), int(minute or 59), tzinfo=JST)
            except ValueError:
                continue
            deadlines.add((deadline, bool(hour)))
    if len(deadlines) == 1:
        deadline, timed = deadlines.pop()
        if deadline < now.replace(second=0, microsecond=0):
            return False
        item['deadline_label'] = deadline.strftime('%m/%d %H:%M' if timed else '%m/%d')
    links = set()
    photos = set()
    terms = re.findall(r'[『「]([^』」]{3,})[』」]', item['title'])
    for n in nodes:
        if n.tag == 'a' and re.search(r'応募フォーム|申込フォーム|抽選に応募|応募はこちら|抽選申込', clean(n.text())):
            url = urljoin(item['url'], n.attrs.get('href') or '')
            dest = urlsplit(url)
            if dest.scheme == 'https' and dest.hostname in (urlsplit(item['url']).hostname,
                    'livepocket.jp', 't.livepocket.jp', 'forms.gle', 'docs.google.com') and not dest.username:
                links.add(url)
        if n.tag == 'img' and any(t in (n.attrs.get('alt') or '') for t in terms):
            photo = canonical_url(item['url'], n.attrs.get('src') or '')
            if photo and photo != item['url']:
                photos.add(photo)
    if len(links) == 1:
        item['application_url'] = links.pop()
    if len(photos) == 1:
        item['product_photo'] = photos.pop()
    return True


def format_post(item):
    tags = post_hashtags(item)
    if item.get('guide_id') == 'lottery-receipt':
        return ('当たったー！🎉✨ スマホも持った📱 靴も履いた👟\n……お財布、まだキッチンにある👛💦\n\n店頭で受け取る日は、出発前に当選通知をもう一度💌\n受取期限と必要な持ち物をチェックしたら、今度こそ行ってきます！🃏\n#トレカ女子 #トレカ抽選')
    if item.get('kind') == 'guide':
        text = '🃏 ' + item['title'] + '\n\n' + item['body']
        suffix = '\n' + tags + '\n参照先👇\n'
        limit = (270 - 23) // 2 - len(suffix)
        if len(text) > limit:
            text = text[:limit - 1] + '…'
        return text + suffix + item['url']
    label = SOURCES[item['source']][0]
    store = item.get('store', '')
    spotlight = item.get('kind') == 'spotlight'
    if not spotlight and '抽選' in item['title']:
        place = store or label
        deadline = item.get('deadline_label', '店舗の告知で確認')
        link = item.get('application_url')
        footer = f"\n\n📍 {place[:32]}\n⏰ 応募締切：{deadline}\n"
        footer += '🔽 応募はこちら' if link else '🔽 応募方法・条件はこちら'
        header = '🎟️ トレカ抽選情報\n'
        budget = max(1, 122 - len(header + footer + tags) - 4)
        title = item['title']
        if len(title) > budget:
            title = title[:budget - 1] + '…'
        return header + title + footer + '\n' + (link or item['url']) + '\n\n' + tags
    category = '🃏 商品ピックアップ' if spotlight else ('🎟️ 抽選のお知らせ' if '抽選' in item['title'] else '📣 新着のお知らせ')
    before = f'{category}｜{label}{("・" + store) if store else ""}\n'
    after = f'\n発表日：{item["published"]}\n' + ('新着速報ではありません。詳細は公式へ👇\n' if spotlight else ('締切と受取場所はこちら👇\n' if '抽選' in item['title'] else '詳しくはこちら👇\n'))
    after += tags + '\n'
    # Reserve the tag budget before truncation; never drop mandatory tags.
    limit = (270 - 23) // 2 - len(before) - len(after)
    title = item['title']
    if len(title) > limit:
        title = title[:limit - 1] + '…'
    return before + title + after + item['url']


def update_state(state, batches, now):
    state.setdefault('version', 1)
    state.setdefault('sources', {})
    state.setdefault('items', {})
    stats = {}
    for source, items in batches.items():
        first = source not in state['sources']
        new_count = 0
        for item in items:
            if item['key'] in state['items']:
                continue
            status = 'baseline' if first else ('ready' if eligible(item, now) else 'ignored')
            state['items'][item['key']] = dict(item, status=status, discovered_at=now.isoformat())
            new_count += status == 'ready'
        state['sources'][source] = {'checked_at': now.isoformat(), 'count': len(items),
                                    'latest_date': max(i['published'] for i in items)}
        stats[source] = {'baseline_created': first, 'count': len(items), 'new_candidates': new_count,
                         'latest_date': state['sources'][source]['latest_date']}
    for item in state['items'].values():
        if item['status'] == 'ready' and any(other.get('closed') and other['url'] == item['url']
                                             for batch in batches.values() for other in batch):
            item['status'] = 'expired'
        if item['status'] == 'ready' and not eligible(item, now):
            item['status'] = 'expired'
    return stats


def select_candidate(state, now, daily_limit, available_sources=None):
    if any(i['status'] in ('sending', 'uncertain') for i in state['items'].values()):
        return None  # Require reconciliation before any more posts.
    today = now.astimezone(JST).date().isoformat()
    count = sum(i.get('attempt_date') == today for i in state['items'].values())
    if count >= daily_limit or not 8 <= now.astimezone(JST).hour < 23:
        return None
    ready = [i for i in state['items'].values() if i['status'] == 'ready' and eligible(i, now)
             and (available_sources is None or i['source'] in available_sources)]
    return sorted(ready, key=lambda i: (i['published'], i['key']), reverse=True)[0] if ready else None


def save(state):
    STATE.parent.mkdir(exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(STATE)


def checkpoint(*extra_paths):
    # Git must acknowledge durable state before a mutation is attempted.
    subprocess.run(['git', 'add', 'data/state.json', *extra_paths], cwd=ROOT, check=True)
    changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode
    if changed == 0:
        return
    if changed != 1:
        raise RuntimeError('Cannot check staged state')
    subprocess.run(['git', 'commit', '-m', 'chore: persist news watcher state'], cwd=ROOT, check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=ROOT, check=True)


class BufferRateLimit(RuntimeError):
    pass


def buffer_query(query):
    budget=ROOT/'data/buffer-api-budget.json'
    now=datetime.now(JST)
    if budget.exists():
        saved=json.loads(budget.read_text())
        if saved.get('resume_at') and now<datetime.fromisoformat(saved['resume_at']):
            raise BufferRateLimit('Buffer cooldown until '+saved['resume_at'])
    key = os.environ.get('BUFFER_API_KEY', '').strip().lstrip('\ufeff')
    if not key:
        raise ValueError('BUFFER_API_KEY missing')
    request = Request('https://api.buffer.com', data=json.dumps({'query': query}).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
    from urllib.error import HTTPError
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        if exc.code!=429:
            raise
        raw=exc.headers.get('Retry-After','3600')
        try:
            delay=max(60,int(raw))
        except ValueError:
            delay=3600
        budget.write_text(json.dumps({'checked_at':now.isoformat(),'resume_at':(now+timedelta(seconds=delay)).isoformat(),'http_status':429},indent=2)+'\n')
        checkpoint('data/buffer-api-budget.json')
        raise BufferRateLimit('Buffer requested cooldown for '+str(delay)+' seconds') from None
    if not isinstance(result, dict) or result.get('errors') or not result.get('data'):
        raise ValueError('Buffer rejected request; response is not logged')
    return result['data']


def check_channel(channel_id):
    query = 'query { channel(input: { id: ' + json.dumps(channel_id) + ' }) { id name service } }'
    channel = buffer_query(query).get('channel', {})
    if channel.get('id') != channel_id or channel.get('service') != 'twitter':
        raise ValueError('Configured X channel could not be confirmed')
    return {'id': channel['id'], 'name': channel.get('name'), 'service': channel['service']}


def publishing_started(config, now):
    return now.astimezone(JST).date().isoformat() >= config.get('start_date_jst', '0001-01-01')


NEWS_IMAGE_URL = "https://raw.githubusercontent.com/ncb1310/toreca-news-bot/main/assets/news-brand.png"


def send(item, channel_id):
    # No retries: a timeout after acceptance cannot safely be distinguished from failure.
    image_url = item.get('image_url', '')
    if not image_url.startswith('https://raw.githubusercontent.com/ncb1310/toreca-news-bot/') or '/assets/generated/' not in image_url:
        raise ValueError('A post-specific published image is mandatory')
    query = ('mutation { createPost(input: { text: ' + json.dumps(format_post(item)) +
             ', channelId: ' + json.dumps(channel_id) +
             ', schedulingType: automatic, mode: shareNow, assets: [{ image: { url: ' + json.dumps(image_url) + ' } }], needsApproval: false }) {'
             ' ... on PostActionSuccess { post { id } } ... on MutationError { message } } }')
    data = buffer_query(query)
    post = (data.get('createPost') or {}).get('post')
    if not isinstance(post, dict) or not post.get('id'):
        raise ValueError('Buffer did not confirm creation')
    return post['id']


def publish_card(item, now):
    from post_cards import image_name, render_card
    if item.get('guide_id') == 'lottery-receipt':
        relative = 'assets/toreca/lottery-receipt.jpg'
        signature = b'\xff\xd8\xff'
    else:
        signature = b'\x89PNG\r\n\x1a\n'
        relative = 'assets/generated/' + image_name(item)
        label = 'トレカの基礎と確認ポイント' if item.get('kind') == 'guide' else SOURCES[item['source']][0]
        destination = ROOT / relative
        photo_saved = False
        if item.get('product_photo'):
            from io import BytesIO
            from PIL import Image, ImageOps
            try:
                with urlopen(Request(item['product_photo'], headers={'User-Agent': AGENT}), timeout=15) as response:
                    if not canonical_url(item['url'], response.url):
                        raise ValueError('Unexpected photo host')
                    data = response.read(8_000_001)
                if len(data) <= 8_000_000:
                    with Image.open(BytesIO(data)) as photo:
                        if photo.width * photo.height <= 16_000_000 and min(photo.size) >= 200:
                            photo = ImageOps.exif_transpose(photo).convert('RGBA')
                            photo.thumbnail((1200, 1200))
                            canvas = Image.new('RGB', photo.size, 'white')
                            canvas.paste(photo, mask=photo.getchannel('A'))
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            canvas.save(destination, format='PNG')
                            photo_saved = True
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
        if not photo_saved:
            render_card(item, label, now, destination)
        checkpoint(relative)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    image_url = 'https://raw.githubusercontent.com/ncb1310/toreca-news-bot/' + revision + '/' + relative
    with urlopen(Request(image_url, headers={'User-Agent': AGENT}), timeout=25) as response:
        if response.read(len(signature)) != signature:
            raise ValueError('Published image could not be verified')
    item['image_url'] = image_url


def reconcile_publications(state, now):
    from editorial import records
    pending = [i for i in records(state) if i.get('status') == 'accepted'
               and i.get('buffer_post_id') and (i.get('publication_result') or {}).get('status') not in ('sent', 'error')]
    pending = [i for i in pending if not i.get('scheduled_at') or datetime.fromisoformat(i['scheduled_at']) <= now]
    for item in pending[:3]:
        # A failed read never changes the accepted mutation into a new send.
        if item.get('publication_checks', 0) >= 6:
            continue
        item['publication_checks'] = item.get('publication_checks', 0) + 1
        try:
            post = buffer_query('query { post(input: { id: ' + json.dumps(item['buffer_post_id']) +
                                ' }) { id status sentAt externalLink assets { mimeType source } } }').get('post')
            if post:
                item['publication_result'] = post
                item['publication_checked_at'] = now.isoformat()
        except Exception:
            item['publication_read_error'] = True


def prepare_item(item):
    if item['source'] == 'hobby':
        # The homepage truncates headlines. Read the full official headline once.
        root = DOM(official_page(item['url'])).root
        headline = next((clean(n.text()) for n in root.walk() if n.tag == 'h3'
                         and re.match(r'【\d{4}\.\d{1,2}\.\d{1,2}】', clean(n.text()))), None)
        if not headline:
            raise ValueError('Full official headline could not be verified')
        headline = re.sub(r'^【[^】]+】', '', headline).strip()
        if re.search(r'応募は終了|受付終了|販売終了|抽選終了', headline):
            item['status'] = 'expired'
            return False
        item['title'] = headline
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Requires GitHub Actions and persistent checkpoints')
    args = parser.parse_args()
    config = json.loads((ROOT / 'config.json').read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = datetime.now(JST)
    batches, errors = {}, {}
    for source, (_, url) in SOURCES.items():
        try:
            batches[source] = parse(source, official_page(url))
        except HTTPError as exc:
            errors[source] = 'HTTP ' + str(exc.code)
        except Exception as exc:
            errors[source] = type(exc).__name__  # No response bodies or credentials.
    stats = update_state(state, batches, now)
    report = {'checked_at': now.isoformat(), 'sources': stats, 'source_errors': errors,
              'posting_enabled': config['posting_enabled'], 'channel': None, 'created_post_id': None}
    report['stale_sources'] = [name for name, value in stats.items()
                               if (now.date() - date.fromisoformat(value['latest_date'])).days > 7]
    if args.live and os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('--live is supported only inside GitHub Actions')
    # A plain preview must never change the durable baseline.
    from editorial import records, select_fallback
    history = records(state)
    blocked = any(i.get('status') in ('sending', 'uncertain') for i in history)
    count_today = sum(i.get('attempt_date') == now.date().isoformat() for i in history)
    recent_attempt = any(i.get('attempted_at') and now - datetime.fromisoformat(i['attempted_at']) < timedelta(minutes=config.get('min_post_interval_minutes', 55)) for i in history)
    candidate = None
    if not blocked and count_today < config['max_posts_per_day'] and not recent_attempt:
        candidate = select_candidate(state, now, config['max_posts_per_day'], batches.keys())
        if candidate is None and config.get('editorial_enabled'):
            candidate = select_fallback(state, batches, now, config)
            if candidate:
                state.setdefault('editorial_posts', {})[candidate['key']] = candidate
    if args.live:
        reconcile_publications(state, now)
        save(state)
        checkpoint()
        cached = state.get('channel_check', {})
        if cached.get('date') != now.date().isoformat() or candidate:
            channel = check_channel(config['channel_id'])
            state['channel_check'] = {'date': now.date().isoformat(), 'channel': channel}
            save(state)
            checkpoint()
        report['channel'] = state['channel_check']['channel']
    report['next_candidate'] = format_post(candidate) if candidate else None
    report['needs_reconciliation'] = blocked
    report['today_attempts'] = count_today
    report['daily_target'] = config.get('daily_target')
    report['publishing_started'] = publishing_started(config, now)
    if args.live and config['posting_enabled'] and publishing_started(config, now) and candidate:
        try:
            if candidate.get('kind') != 'guide' and not prepare_item(candidate):
                save(state)
                checkpoint()
                print('公式ページで終了を確認したため投稿を見送りました。')
                return 0
            # Verify the source page is still reachable immediately before publication.
            # Do not turn archived product announcements into current stock claims.
            if candidate.get('kind') not in ('guide', 'spotlight') and '抽選' in candidate['title']:
                if not lottery_details(candidate, official_page(candidate['url']), now):
                    candidate['status'] = 'expired'
                    save(state)
                    checkpoint()
                    return 0
            elif candidate['source'] != 'hobby':
                official_page(candidate['url'])
        except Exception as exc:
            candidate['status'] = 'verification_failed'
            candidate['verification_failed_date'] = now.date().isoformat()
            candidate['verification_error'] = type(exc).__name__
            save(state)
            checkpoint()
            print('::warning::出典を再確認できず見送り。次回は別の候補を選択します。')
            return 0
        if candidate.get('kind') == 'guide':
            report['candidate_kind'] = 'guide'
        publish_card(candidate, now)  # Failure here means no Buffer mutation.
        candidate['status'] = 'sending'
        candidate['attempt_date'] = now.date().isoformat()
        candidate['attempted_at'] = now.isoformat()
        save(state)
        checkpoint()  # If this fails, the following API call is never reached.
        try:
            candidate['buffer_post_id'] = send(candidate, config['channel_id'])
            candidate['status'] = 'accepted'
            report['created_post_id'] = candidate['buffer_post_id']
        except Exception:
            candidate['status'] = 'uncertain'
            save(state)
            checkpoint()
            raise RuntimeError('投稿結果が不明なため自動再送を停止。Buffer画面で確認してください。') from None
        save(state)
        checkpoint()
        reconcile_publications(state, now)
        save(state)
        checkpoint()
        report['publication_result'] = candidate.get('publication_result')
    report_path = ROOT / 'report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        print('::warning::一部の情報源を取得できませんでした。取得成功した情報源のみ処理します。実行概要のsource_errorsを確認してください。')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as handle:
            handle.write('## トレカ公式情報の確認結果\n\n```json\n' + json.dumps(report, ensure_ascii=False, indent=2).replace('```', '') + '\n```\n')
    if not batches or blocked:
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('失敗：' + type(exc).__name__ + '。Actionsの実行概要を確認してください。', file=sys.stderr)
        sys.exit(1)

