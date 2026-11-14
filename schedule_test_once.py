"""Single authorized launch post, with a durable no-retry marker."""
import json
from datetime import datetime
import news_bot as bot

TEXT = """おはようございます👓⚡\n\n今日もポケカ・ワンピカードの公式告知をチェック！\n予約・抽選・再販情報は、受付状況や応募条件を公式ページで確認してね。\n\n※この投稿は時刻指定の予約配信を確認するための投稿です。"""

def main():
    config = json.loads((bot.ROOT / 'config.json').read_text())
    channel = bot.check_channel(config['channel_id'])
    if channel.get('name', '').lstrip('@').lower() != 'toreca_joshi':
        raise RuntimeError('New handle does not match; nothing posted')
    state = json.loads(bot.STATE.read_text())
    operations = state.setdefault('manual_operations', {})
    operation = 'scheduled-test-toreca-joshi-20261115-0805'
    if operation in operations:
        print('Already attempted; no automatic retry')
        return
    entry = {'status': 'sending', 'channel': channel, 'text': TEXT,
             'attempted_at': datetime.now(bot.JST).isoformat()}
    operations[operation] = entry
    bot.save(state)
    bot.checkpoint()
    query = ('mutation { createPost(input: { text: ' + json.dumps(TEXT) +
             ', channelId: ' + json.dumps(config['channel_id']) +
             ', schedulingType: automatic, mode: customScheduled, dueAt: "2026-11-14T23:05:00Z", assets: [], needsApproval: false }) {'
             ' ... on PostActionSuccess { post { id } } ... on MutationError { message } } }')
    try:
        data = bot.buffer_query(query)
        post = (data.get('createPost') or {}).get('post')
        if not post or not post.get('id'):
            raise RuntimeError('Creation not confirmed')
        entry.update(status='accepted', buffer_post_id=post['id'])
    except Exception:
        entry['status'] = 'uncertain'
        bot.save(state)
        bot.checkpoint()
        raise RuntimeError('Result unknown; do not retry') from None
    bot.save(state)
    bot.checkpoint()
    print(json.dumps(entry, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
