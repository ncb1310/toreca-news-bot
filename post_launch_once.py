"""Single authorized launch post, with a durable no-retry marker."""
import json
from datetime import datetime
import news_bot as bot

TEXT = """買い逃し・応募忘れ、減らしていこう👓⚡

トレカ女子速報では、ポケカ・ワンピカードの予約・抽選・再販に関する公式告知をチェックしてお届けします！

気になる情報は、公式リンクから受付状況や応募条件を確認してね。
※非公式の情報アカウントです。"""

def main():
    config = json.loads((bot.ROOT / 'config.json').read_text())
    channel = bot.check_channel(config['channel_id'])
    if channel.get('name', '').lstrip('@').lower() != 'toreca_joshi':
        raise RuntimeError('New handle does not match; nothing posted')
    state = json.loads(bot.STATE.read_text())
    operations = state.setdefault('manual_operations', {})
    operation = 'launch-confirmation-toreca-joshi-20261114'
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
             ', schedulingType: automatic, mode: shareNow, assets: [], needsApproval: false }) {'
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
