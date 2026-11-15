"""One image publication test; never repeat an uncertain mutation."""
import json
import time
from datetime import datetime
import news_bot as bot

TEXT = """画像付きでお届けする準備もできました👓⚡

ポケカ・ワンピカードの予約・抽選・再販を中心に、公式告知をチェックしてお届けします。
販売先や応募条件は、各投稿の公式リンクで確認してね。

※非公式の情報アカウントです。"""

def main():
    config = json.loads((bot.ROOT / 'config.json').read_text())
    channel = bot.check_channel(config['channel_id'])
    if channel.get('name', '').lstrip('@').lower() != 'toreca_joshi':
        raise RuntimeError('Wrong target; nothing posted')
    state = json.loads(bot.STATE.read_text())
    ops = state.setdefault('manual_operations', {})
    key = 'image-publication-test-toreca-joshi-20261115'
    entry = ops.get(key)
    if entry is None:
        entry = {'status': 'sending', 'attempted_at': datetime.now(bot.JST).isoformat(),
                 'image_url': bot.NEWS_IMAGE_URL}
        ops[key] = entry
        bot.save(state)
        bot.checkpoint()
        query = ('mutation { createPost(input: { text: ' + json.dumps(TEXT) +
                 ', channelId: ' + json.dumps(config['channel_id']) +
                 ', schedulingType: automatic, mode: shareNow, assets: [{ image: { url: ' +
                 json.dumps(bot.NEWS_IMAGE_URL) + ' } }], needsApproval: false }) {'
                 ' ... on PostActionSuccess { post { id } } ... on MutationError { message } } }')
        try:
            result = bot.buffer_query(query)
            post = (result.get('createPost') or {}).get('post')
            if not post or not post.get('id'):
                raise RuntimeError('Not confirmed')
            entry.update(status='accepted', buffer_post_id=post['id'])
        except Exception:
            entry['status'] = 'uncertain'
            bot.save(state)
            bot.checkpoint()
            raise RuntimeError('Unknown outcome; do not resend') from None
        bot.save(state)
        bot.checkpoint()
    if not entry.get('buffer_post_id'):
        raise RuntimeError('Previous uncertain attempt; no resend')
    for attempt in range(8):
        query = ('query { post(input: { id: ' + json.dumps(entry['buffer_post_id']) +
                 ' }) { id status sentAt externalLink assets { mimeType source } } }')
        post = bot.buffer_query(query).get('post')
        entry['publication_result'] = post
        if post and post.get('status') in ('sent', 'error'):
            break
        time.sleep(5)
    bot.save(state)
    bot.checkpoint()
    print(json.dumps(entry, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
