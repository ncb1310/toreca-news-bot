"""Fresh official product spotlights and a finite, non-daily-repeating guide bank."""
from datetime import date, datetime, timedelta
import hashlib
import re

POKE_RULES = 'https://www.pokemon-card.com/howtoplay/'
POKE_REG = 'https://www.pokemon-card.com/rules/regulation/'
POKE_SEARCH = 'https://www.pokemon-card.com/card-search/'
ONE_RULES = 'https://www.onepiece-cardgame.com/rules/'
# Original editorial checklists, not quotations or availability claims.
# Entries are not repeated within 14 days. Exhaustion never bypasses the cooldown.
GUIDES = [
    ('lottery-dates', '抽選の締切、3つを分けよう', ['応募締切', '当選発表日', '当選後の購入期限'], '応募できても、購入期限を過ぎると買えない場合がある。告知を見たら3つの日付を別々にメモしておこう。', 'https://www.pokemoncenter-online.com/?main_page=lottery'),
    ('lottery-store', '抽選は「どの店舗か」まで確認', ['応募する店舗', '受け取る店舗', '来店が必要か'], 'チェーン店の告知でも店舗限定の場合がある。店名と受取方法まで確認してから応募しよう。', 'https://www.c-labo.jp/blog/'),
    ('lottery-conditions', '応募前のチェックリスト', ['対象商品・数量', '応募できる人の条件', '重複応募の扱い'], '応募フォームを開く前に、公式告知の条件を読む。購入履歴や会員登録などの条件は、企画ごとに確認しよう。', 'https://www.pokemoncenter-online.com/?main_page=lottery'),
    ('lottery-entry', '「応募完了」と「購入完了」は別', ['応募を受け付けたか', '当選しているか', '購入手続きが終わったか'], '抽選は段階ごとに確認しよう。メールが届いたら、何の完了通知なのかまで読んでおくと安心。', 'https://www.pokemoncenter-online.com/?main_page=lottery'),
    ('retail-status', '「再販告知」だけで急がない', ['告知された日付', '販売開始の日時', '今の受付状況'], '過去の再販記事が流れてくることもある。リンク先の日付と受付状況を見てから動こう。', 'https://www.furu1.net/news/'),
    ('product-identity', '同じシリーズでも商品を確認', ['正式な商品名', 'パック・BOX・セットの違い', '商品内容の説明'], '名前が似ている商品は、正式名称と内容を並べて確認。欲しいものと注文するものが同じか、最後に見直そう。', 'https://www.pokemon-card.com/products/'),
    ('poke-sixty', 'ポケカの60枚デッキ入門', ['カードを60枚に組む', '使えるカードの範囲を確認', '公式のあそびかたを読む'], '60枚デッキを作るときは、枚数とレギュレーションをセットで確認。最初は公式の「あそびかた」が入口になるよ。', POKE_RULES),
    ('poke-regulation', '買う前にレギュレーション確認', ['参加したい大会の形式', 'その形式で使えるカード', '公式の最新案内'], '欲しいカードが大会で使えるかは、参加する大会のレギュレーション次第。購入前に公式で確認しておこう。', POKE_REG),
    ('poke-search', 'カード名だけで迷ったら', ['正式なカード名', 'カード番号・収録商品', 'カードに書かれた効果'], '同じ名前でもカードの内容が違うことがある。公式カード検索で、探している1枚を絞り込もう。', POKE_SEARCH),
    ('poke-energy', '基本エネルギーと4枚ルール', ['60枚デッキが対象', '同じ名前は原則4枚まで', '基本エネルギーなど例外あり'], 'ポケカの60枚デッキは、同じ名前のカードを原則4枚まで。基本エネルギーやカード固有の指定など、例外も公式で確認しよう。', POKE_RULES),
    ('poke-starter', 'はじめのデッキ、内容を見よう', ['デッキとして遊べる商品か', '付属する道具は何か', '別に必要なものはあるか'], '最初の買い物は、商品名だけで決めず内容までチェック。遊ぶために必要なものが揃うか見ておこう。', 'https://www.pokemon-card.com/products/'),
    ('poke-tool', '初対戦の前に道具を確認', ['デッキ', 'ダメカン・マーカー類', 'コインなど必要な道具'], '初めて遊ぶ前に、公式のあそびかたで必要な道具を確認。手元のセットに何が付いているかも見直しておこう。', POKE_RULES),
    ('one-deck', 'ワンピカードのデッキ準備', ['リーダーカード1枚', 'デッキ50枚', 'ドン!!カード10枚'], 'ONE PIECEカードゲームの基本の準備。リーダー・デッキ・ドン!!カードを分けて数えると確認しやすいよ。', ONE_RULES),
    ('one-color', 'リーダーからデッキを考える', ['使いたいリーダーを決める', 'リーダーの色を確認', '構築条件を公式で確認'], 'ワンピカードは、リーダーを決めてからカードを探すと整理しやすい。構築の細かな条件は公式ルールへ。', ONE_RULES),
    ('one-number', '同名カードは番号も見よう', ['カード名', 'カード番号', 'カードの効果'], 'ワンピカードを探すときは、名前とカード番号をセットで。似た見た目や同じキャラクターでも、内容を確認しよう。', 'https://www.onepiece-cardgame.com/cardlist/'),
    ('one-start', 'ワンピカードを始める前に', ['公式のルールを読む', '必要なデッキを準備', 'カードの効果を確認'], '最初から全部覚えなくても大丈夫。公式のルールページを開きながら、ひとつずつ準備していこう。', ONE_RULES),
    ('lottery-receipt', '当選後の受取条件をチェック', ['受取期間', '本人確認の案内', '必要な当選通知'], '当選したら、購入期限に加えて受取条件も確認。必要なものは店舗や企画によって異なるよ。', 'https://www.c-labo.jp/blog/'),
    ('lottery-result', '当選発表日の確認ポイント', ['どこで結果を見るか', 'いつから確認できるか', '購入期限はいつか'], '結果はメール・アプリ・サイトなど、企画ごとに案内が違う。応募時点で確認方法をメモしておこう。', 'https://www.pokemoncenter-online.com/?main_page=lottery'),
    ('online-order', '通販の注文前、ここを見直す', ['商品の正式名称と数量', '配送・受取方法', '送料を含む支払内容'], '注文確定の前に一度だけ見直そう。パックとBOX、配送と店頭受取など、選択内容を確認しておくと安心。', 'https://www.pokemoncenter-online.com/'),
    ('lottery-calendar', '抽選管理は1件1メモで', ['商品名・店舗名', '応募締切と発表日', '当選後の購入期限'], '抽選を複数追うなら、1件ずつ記録。別の商品の購入期限と取り違えないよう、店名も一緒に残そう。', 'https://www.pokemoncenter-online.com/?main_page=lottery'),
    ('official-source', '販売情報は出典まで確認', ['メーカーか販売店の公式か', '対象の店舗・地域', 'ページの更新日'], 'まとめ投稿は情報を探す入口。応募や購入の前には、出典の公式ページで最新条件を確認しよう。', 'https://www.pokemon-card.com/info/'),
    ('poke-effects', 'カードの使い方で迷ったら', ['カード名で探す', '効果を読み直す', '公式Q&Aも確認'], '対戦中に迷った効果は、公式カード検索やQ&Aで確認しよう。別のカードの説明と混ぜないのがポイント。', POKE_SEARCH),
    ('one-products', 'ワンピの商品選びは内容から', ['商品名と商品番号', '収録・セット内容', '発売日の公式案内'], 'ブースターパックとスタートデッキは、商品ページの内容を見比べよう。遊びたい目的に合うか確認して選ぼう。', 'https://www.onepiece-cardgame.com/products/'),
    ('lottery-last-check', '締切直前に見直す3点', ['応募は完了しているか', '対象商品に間違いはないか', '公式のお知らせに変更はないか'], '締切前は新しく応募するだけでなく、完了状況も確認。受付時間や条件の更新がないか公式案内を見直そう。', 'https://www.c-labo.jp/blog/'),
]


def records(state):
    return list(state.get('items', {}).values()) + list(state.get('editorial_posts', {}).values())


def recently_used(state, now, url=None, guide_id=None, days=14):
    for item in records(state):
        matches = (url and item.get('url') == url) or (guide_id and item.get('guide_id') == guide_id)
        if matches and item.get('verification_failed_date') == now.date().isoformat():
            return True
        if not item.get('attempt_date'):
            continue
        if (now.date() - date.fromisoformat(item['attempt_date'])).days >= days:
            continue
        if matches:
            return True
    return False


def select_fallback(state, batches, now, config):
    today = now.date().isoformat()
    history = records(state)
    if any(i.get('status') in ('sending', 'uncertain') for i in history):
        return None
    if not 8 <= now.hour < 23:
        return None
    attempts = [i for i in history if i.get('attempt_date') == today]
    if len(attempts) >= min(config.get('daily_target', 10), config['max_posts_per_day']):
        return None
    # Pace planned material across the day; do not fill the day's allowance at 08:00.
    expected_by_now = min(config.get('daily_target', 10), 1 + (now.hour - 8) * config.get('daily_target', 10) // 15)
    if len(attempts) >= expected_by_now:
        return None
    for item in history:
        if item.get('attempted_at') and now - datetime.fromisoformat(item['attempted_at']) < timedelta(minutes=config.get('min_post_interval_minutes', 55)):
            return None
    products = []
    seen = set()
    for source in ('pokemon', 'onepiece'):
        for item in sorted(batches.get(source, []), key=lambda x: x['published'], reverse=True):
            if item['url'] in seen:
                continue
            seen.add(item['url'])
            age = (now.date() - date.fromisoformat(item['published'])).days
            if not 0 <= age <= config.get('catchup_days', 30) or item.get('category') not in ('商品', 'PRODUCTS'):
                continue
            if item.get('closed') or re.search(r'終了|中止|本日|今日|明日|今夜|お詫び|誤り|訂正|不具合|価格改定|大会|チャンピオン', item['title']):
                continue
            # Historical sales/lottery announcements must never be presented as open.
            if re.search(r'抽選|予約|受注|再販|再入荷|販売開始', item['title']):
                continue
            if recently_used(state, now, url=item['url']):
                continue
            products.append(item)
    if products:
        chosen = dict(sorted(products, key=lambda x: (x['published'], x['key']), reverse=True)[0])
        chosen.update(kind='spotlight', status='ready', key='spotlight-' + chosen['key'])
        return chosen
    if sum(i.get('kind') == 'guide' for i in attempts) >= config.get('editorial_max_per_day', 4):
        return None
    for guide_id, title, bullets, body, url in GUIDES:
        if recently_used(state, now, guide_id=guide_id):
            continue
        key = hashlib.sha256((today + guide_id).encode()).hexdigest()
        return dict(key='guide-' + key, guide_id=guide_id, kind='guide', status='ready',
                    source='guide', title=title, bullets=bullets, body=body, url=url,
                    published=today)
    return None
