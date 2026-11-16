"""Independent Kingshot publisher: approved images, public sources, durable intents."""
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
import re
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import news_bot as shared

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'data/kingshot-state.json'
APP = 'https://apps.apple.com/us/app/kingshot/id6739554056'
LOOKUP = 'https://itunes.apple.com/lookup?id=6739554056&country=us'
FEED = 'https://www.centurygames.com/feed/'
IMAGE = 'https://raw.githubusercontent.com/ncb1310/toreca-news-bot/main/assets/kingshot/strategy-reference-20261116.jpg'
TAGS = '\n#キングショット #Kingshot'

# Independently written Japanese summaries, checked against the developer's
# US App Store version 1.14.16 notes dated Oct 19. These are existing features,
# never labeled a new patch, an unannounced hero ability or kingdom schedule.
GUIDES = [
 ('first-hero', '編成を組み直すときの小ワザ⚔️', '編成画面では、先頭の英雄だけを個別に外せるようになっています。毎回全員を入れ替える前に確認してみて。'),
 ('formation', '編成の選択肢、見直してる？', '米公式の更新説明では、都市センターのレベルに応じて追加の編成が解放されると案内されています。自分の画面で解放状況を確認しよう。'),
 ('fishing-guide', '釣り大会の収集要素もチェック🎣', '条件達成で海藻の図鑑が解放され、収集の進み具合に応じた報酬が案内されています。詳細な条件は大会画面で確認を。'),
 ('fishing-cast', '釣り大会の投げ方を確認🎣', '米公式の更新説明には、進行条件を満たすとPower Castに10倍の選択肢が追加されるとあります。常に全員が使えるとは限らないので画面で確認しよう。'),
 ('fishing-season', '釣り大会のミッションも忘れずに🎣', 'シーズンミッションで得られる釣りポイントと、島の装飾品の交換をチェック。開催中の条件・交換内容はゲーム内が基準です。'),
 ('fishing-claim', '釣り大会の受取漏れ対策🎣', '報酬の一括受取が更新説明に載っています。個別の報酬だけでなく、受取ボタンや未受領表示も見直しておこう。'),
 ('avatar', '高解像度アバターの表示を見直そう', 'ほかの領主に高解像度の画像を見せたくない場合、設定のアバター項目で変更できます。米公式の更新説明に記載された機能です。'),
 ('avatar-upload', 'アバターを高解像度で表示したいとき', '米公式の更新説明では、機能を有効にするため画像を再アップロードする必要があると案内されています。表示されないときの確認ポイントに。'),
 ('avatar-frame', 'アバター枠との相性、先に確認', 'カスタムアバターの確認画面には、枠付きの見え方をプレビューする選択肢が案内されています。設定する前に表示を見直そう。'),
 ('notice-draft', '同盟のお知らせ、下書きも活用📋', '予約したお知らせの編集では、確定せず画面を離れたときに最新の下書きを保存する機能が案内されています。公開済みとの取り違えには注意しよう。'),
 ('vote-ranks', '投票を作るときの確認ポイント📋', '投票を始める際、参加できる同盟ランクを選べると米公式が案内しています。投票内容と対象者をセットで確認しておこう。'),
 ('war-filter', '同盟戦争の絞り込みを見直そう', '米公式の更新説明には、集結主レベルを一覧から選ぶ方式や、フィルターでのTruegoldレベル表示が記載されています。検索条件を確認しよう。'),
 ('war-notification', '通知が多いと感じたら設定を確認', '同盟戦争にはイベント情報のリマインダーや戦闘通知を調整する機能が案内されています。必要な情報を受け取れる設定に整えよう。'),
 ('island-fountain', '島の育成が進んだら確認したいこと🏝️', '生命の泉を最大まで育てると、島の探索で新しいミッションが解放されると米公式が案内しています。達成後のミッション欄も見ておこう。'),
 ('island-label', '島の装飾品、育成状況を見分けよう🏝️', '米公式の更新説明では、最大まで育てた装飾品にMax表示が付く改善が案内されています。交換・育成前の見直しに使いたい機能です。'),
 ('vip-days', 'ログイン日数の表示も切り替えられる', 'VIPページでは連続ログイン日数と累計ログイン日数を切り替えて確認できると案内されています。表示の意味を取り違えないよう確認を。'),
 ('castle-duration', '王城戦の状況確認に使える表示🏰', '米公式の更新説明には、砲塔の詳細画面に同盟の占領時間ランキングを表示する項目が追加されたとあります。実際の画面で確認してみよう。'),
 ('recruit-count', '英雄募集の回数を選びたいとき', '米公式の更新説明では、全て使用する操作がMulti Recruitへ変わり、募集回数を選べるようになったと案内されています。確定前に回数を確認しよう。'),
 ('chat-bottom', 'チャットの最新位置へ戻りたいとき', '過去の会話を見ていて新着がない場合、最新位置へ移動するボタンが表示されると案内されています。流れを追い直すときの確認ポイントに。'),
 ('battle-chat', '戦場に入った後の通知を確認⚔️', '米公式は、一部の戦場に入ると王国・同盟のお知らせやチャット放送を自動でミュートする調整を案内しています。重要な指示の確認方法も整えておこう。'),
]


def save(state):
    STATE.parent.mkdir(exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(STATE)


def checkpoint(state):
    save(state)
    shared.checkpoint('data/kingshot-state.json')


def collect(now):
    snapshots, errors, candidates = {}, {}, []
    try:
        app = json.loads(shared.fetch(LOOKUP))['results'][0]
        if str(app.get('trackId')) != '6739554056':
            raise ValueError('Wrong app')
        snapshots['appstore'] = app['version']
        released = datetime.fromisoformat(app['currentVersionReleaseDate'].replace('Z','+00:00'))
        labels = [ja for en, ja in [('Formation','編成'),('Fishing Tournament','釣り大会'),('Hero Recruitment','英雄募集'),('Alliance','同盟機能')] if en.lower() in app.get('releaseNotes','').lower()]
        if timedelta(0) <= now-released <= timedelta(days=3):
            candidates.append(dict(key='release-'+app['version'], source='appstore', identity=app['version'],
                text='【海外公式アプリ更新】\n米App Storeでバージョン'+app['version']+'を確認。\n'+('更新説明の項目：'+'・'.join(labels)+'。\n' if labels else '')+'詳細は公式の更新履歴へ。日本版の反映はゲーム内でも確認を👇\n'+APP+TAGS, image_url=IMAGE))
    except Exception as exc:
        errors['appstore'] = type(exc).__name__
    try:
        root = ET.fromstring(shared.official_page(FEED))
        entries = []
        for item in root.findall('./channel/item'):
            title, url, pub = item.findtext('title',''), item.findtext('link',''), item.findtext('pubDate','')
            if not title.lower().startswith('kingshot') or urlsplit(url).hostname not in ('www.centurygames.com','centurygames.com'):
                continue
            entries.append(url)
            released = parsedate_to_datetime(pub)
            if timedelta(0) <= now-released <= timedelta(days=3):
                # Arbitrary new headlines are not machine-translated without a model.
                # Preserve original title; Japanese framing never invents patch details.
                title = title[:65]
                candidates.append(dict(key='official-'+hashlib.sha256(url.encode()).hexdigest()[:16],source='publisher',identity=url,
                    text='【海外公式のお知らせ】\n原題：'+title+'\n\nKingshotの公式案内が公開されています。内容・対象・期間は出典で確認を👇\n'+url+TAGS,image_url=IMAGE))
        snapshots['publisher'] = entries
    except Exception as exc:
        errors['publisher'] = type(exc).__name__
    return snapshots, errors, candidates


def select(state, candidates, now, config):
    posts = state.get('posts',{})
    if any(p.get('status') in ('sending','uncertain') for p in posts.values()):
        return None
    if not 8 <= now.hour < 23:
        return None
    today = now.date().isoformat()
    used = [p for p in posts.values() if p.get('attempt_date') == today]
    if len(used) >= config['max_posts_per_day']:
        return None
    timestamps = [datetime.fromisoformat(p['attempted_at']) for p in posts.values() if p.get('attempted_at')]
    oneoff = ROOT / 'data/kingshot-fantasy-news-20261116.json'
    if oneoff.exists():
        previous = json.loads(oneoff.read_text())
        if previous.get('attempted_at'):
            timestamps.append(datetime.fromisoformat(previous['attempted_at']))
    if timestamps and now-max(timestamps) < timedelta(minutes=config['min_interval_minutes']):
        return None
    for item in candidates:
        if item['key'] not in posts and item.get('identity') not in state.get('baseline',{}).get(item['source'],[]):
            return item
    expected = min(config['daily_target'],1+(now.hour-8)*config['daily_target']//15)
    if len(used) >= expected:
        return None
    if 8 <= now.hour < 10 and not any(p.get('kind')=='morning' for p in used):
        return dict(key='morning-'+today,kind='morning',text='おはようございます！☀️\n今日もキングショットを楽しんでいきましょう。\n育成も攻略も、自分のペースで。仲間との一日が良い時間になりますように⚔️'+TAGS,
                    image_url=config['morning_images'][now.date().toordinal()%len(config['morning_images'])])
    for guide_id,title,body in GUIDES:
        prior = [p for p in posts.values() if p.get('guide_id')==guide_id and p.get('attempt_date')]
        if prior and min((now.date()-datetime.fromisoformat(p['attempt_date']).date()).days for p in prior)<14:
            continue
        return dict(key='guide-'+guide_id+'-'+today,guide_id=guide_id,kind='guide',text='【既存機能メモ】\n'+title+'\n\n'+body+'\n出典：米公式10/19更新説明\n'+APP+TAGS,image_url=IMAGE)
    return None


def select_image(item, state, config):
    """Use only reviewed, topic-compatible artwork; prefer least-recent use."""
    kind=item.get('kind','news')
    pool=[asset for asset in config.get('media_pool',[])
          if kind in asset.get('allowed_kinds',[])
          and (not asset.get('guide_ids') or item.get('guide_id') in asset['guide_ids'])]
    if not pool:
        return item['image_url']
    last_used={}
    for post in state.get('posts',{}).values():
        url=post.get('image_url')
        at=post.get('attempted_at','')
        if at>last_used.get(url,''):
            last_used[url]=at
    pool.sort(key=lambda asset:(last_used.get(asset['url'],''),asset['id']))
    return pool[0]['url']


def read_result(item):
    if not item.get('post_id'):
        return
    query = 'query { post(input: { id: '+json.dumps(item['post_id'])+' }) { id status sentAt externalLink assets { mimeType source } } }'
    item['publication_result'] = shared.buffer_query(query).get('post')


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Live execution is restricted to the workflow')
    config = json.loads((ROOT/'kingshot-config.json').read_text())
    now = datetime.now(shared.JST)
    state = json.loads(STATE.read_text()) if STATE.exists() else {'posts':{}}
    snapshots, errors, news = collect(now)
    if 'baseline' not in state:
        # First run records old announcements rather than replaying them as news.
        state['baseline'] = {k: ([v] if isinstance(v,str) else v) for k,v in snapshots.items()}
    state['last_checked_at'] = now.isoformat()
    state['source_errors'] = errors
    for item in list(state['posts'].values())[-3:]:
        if item.get('status')=='accepted' and (item.get('publication_result') or {}).get('status') not in ('sent','error'):
            try:
                read_result(item)
            except Exception:
                pass
    candidate = select(state,news,now,config)
    if candidate:
        candidate['image_url']=select_image(candidate,state,config)
    checkpoint(state)
    if candidate and config['posting_enabled']:
        # Verify exact connected account on every send. Never fall back to another.
        channels=[]
        for org in shared.buffer_query('query { account { organizations { id } } }')['account']['organizations']:
            query='query { channels(input: { organizationId: '+json.dumps(org['id'])+' }) { id name service isQueuePaused } }'
            channels.extend(shared.buffer_query(query)['channels'])
        matches=[c for c in channels if c['name'].lstrip('@').lower()=='kingshot5555' and c['service']=='twitter']
        if len(matches)!=1 or matches[0].get('isQueuePaused'):
            raise RuntimeError('Kingshot channel unavailable or paused')
        with urlopen(Request(candidate['image_url'],headers={'User-Agent':shared.AGENT}),timeout=25) as response:
            if response.read(2)!=b'\xff\xd8':
                raise RuntimeError('Approved image unavailable; no text-only post')
        candidate.update(status='sending',attempt_date=now.date().isoformat(),attempted_at=now.isoformat())
        state['posts'][candidate['key']]=candidate
        checkpoint(state)
        query=('mutation { createPost(input: { text: '+json.dumps(candidate['text'])+', channelId: '+json.dumps(matches[0]['id'])+
               ', schedulingType: automatic, mode: shareNow, assets: [{image: {url: '+json.dumps(candidate['image_url'])+
               '}}], needsApproval: false }) { ... on PostActionSuccess { post { id } } ... on MutationError { message } } }')
        try:
            post=shared.buffer_query(query).get('createPost',{}).get('post')
            if not post or not post.get('id'):
                raise RuntimeError('Unconfirmed mutation')
            candidate.update(status='accepted',post_id=post['id'])
        except Exception:
            candidate['status']='uncertain'
            checkpoint(state)
            raise RuntimeError('Outcome uncertain; automatic resend blocked') from None
        checkpoint(state)
        for attempt in range(3):
            try:
                read_result(candidate)
            except Exception:
                break
            if (candidate.get('publication_result') or {}).get('status') in ('sent','error'):
                break
            time.sleep(3)
        checkpoint(state)
    summary=dict(checked_at=now.isoformat(),source_errors=errors,posting_enabled=config['posting_enabled'],
                 today_attempts=sum(p.get('attempt_date')==now.date().isoformat() for p in state['posts'].values()),
                 latest_post=candidate,reference_images='pre-generated approved assets; no unattended imagegen',
                 unsupported_sources=['official Discord','official Facebook','live X timeline'])
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('## Kingshot publisher\n\n'+json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
