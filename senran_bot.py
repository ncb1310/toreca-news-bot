"""Durable, image-required daily greetings for the exact Senran channel."""
import json
import os
import time
from datetime import datetime
from pathlib import Path
import news_bot as shared
from kingshot_bot import verified_image, read_result

ROOT = Path(__file__).resolve().parent
STATE = ROOT/'data/senran-state.json'
SLOTS = [(8,'morning'),(12,'noon'),(18,'evening'),(22,'night')]
BANK = {
 'morning': [
  'おはようございます。\n新しい一日にも、まだ知らない物語が待っています。今日は自分の歩幅で、ゆっくりと。',
  'おはようございます。\n朝の光をひとつ、心の栞に。今日があなたにとって、穏やかな一頁になりますように。',
  'おはようございます。\n始まりの朝は、白い頁に似ています。小さな楽しみをひとつ見つけられますように。',
  'おはようございます。\n遠くまで急がなくても、今日の一歩には意味がある。どうぞ、あなたらしい一日を。',
 ],
 'noon': [
  'こんにちは。\n忙しい時間の合間にも、心に余白を少しだけ。物語をめくるように、ゆっくり息をついていきましょう。',
  'こんにちは。\n何気ない言葉が、ふと心に残ることがあります。今日のあなたにも、そんな出会いがありますように。',
  'こんにちは。\n頁を閉じたあとにも残る景色。そんな物語の余韻を、午後のひと休みに。',
  'こんにちは。\n少し立ち止まる時間も、大切な一頁。午後もどうぞ、無理のない歩幅で。',
 ],
 'evening': [
  'こんばんは。\n一日の終わりに、心をほどく時間を。今日という物語に、小さな安らぎが残りますように。',
  'こんばんは。\n帰り道にも、ひと休みの時間にも。あなたの心に、やさしい余韻が灯りますように。',
  'こんばんは。\n言葉にならなかった気持ちも、今夜はそっと栞に挟んで。穏やかな時間を過ごせますように。',
  'こんばんは。\n今日の頁を振り返る、その少しの時間。小さな喜びがひとつでも見つかりますように。',
 ],
 'night': [
  'おやすみなさい。\n今日の物語はいったんここまで。続きは、また明日のあなたの歩幅で。どうか穏やかな夢を。',
  'おやすみなさい。\n心に残った言葉を、そっと枕元へ。今日を歩いたあなたに、やさしい休息が訪れますように。',
  'おやすみなさい。\nうまくいかなかった頁も、あなたの物語の一部。今夜はゆっくり、心を休めてくださいね。',
  'おやすみなさい。\n本を閉じるように、今日の心にも静かな区切りを。また次の頁で会いましょう。',
 ]
}

def select(state, now):
    due = [(hour,kind) for hour,kind in SLOTS if now.hour >= hour]
    if not due:
        return None
    hour, kind = due[-1]  # Never replay outdated morning greetings at night.
    key = now.date().isoformat()+'-'+kind
    posts = state.get('posts',{})
    if key in posts or any(p.get('status') in ('sending','uncertain') for p in posts.values()):
        return None
    # The user's existing image greeting at noon is already published.
    if key == '2026-11-16-noon':
        return None
    recent = [datetime.fromisoformat(p['attempted_at']) for p in posts.values() if p.get('attempted_at')]
    if recent and (now-max(recent)).total_seconds()<2700:
        return None
    text = BANK[kind][now.date().toordinal()%len(BANK[kind])]
    tag = {'morning':'#おはようございます','noon':'#こんにちは','evening':'#こんばんは','night':'#おやすみなさい'}[kind]
    return dict(key=key,kind=kind,text=text+'\n\n'+tag+' #創作 #小説',
                image_url='https://raw.githubusercontent.com/ncb1310/toreca-news-bot/main/assets/senran/'+kind+'.jpg')

def checkpoint(state):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    shared.checkpoint('data/senran-state.json')

def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Live execution requires durable workflow checkpoints')
    now=datetime.now(shared.JST)
    state=json.loads(STATE.read_text()) if STATE.exists() else {'posts':{}}
    for post in list(state['posts'].values())[-4:]:
        if post.get('status')=='accepted' and (post.get('publication_result') or {}).get('status') not in ('sent','error'):
            read_result(post)
    candidate=select(state,now)
    state['last_checked_at']=now.isoformat()
    checkpoint(state)
    if not candidate:
        print('No current greeting due; no replay or duplicate.')
        return
    channels=[]
    for org in shared.buffer_query('query { account { organizations { id } } }')['account']['organizations']:
        q='query { channels(input: { organizationId: '+json.dumps(org['id'])+' }) { id name service isQueuePaused } }'
        channels.extend(shared.buffer_query(q)['channels'])
    matches=[c for c in channels if c['name'].lstrip('@').lower()=='senran1515' and c['service']=='twitter']
    if len(matches)!=1 or matches[0].get('isQueuePaused'):
        raise RuntimeError('Exact Senran X channel unavailable or paused')
    candidate['image_url']=verified_image(candidate,state,{},now)
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
        raise RuntimeError('Uncertain send; automatic resend blocked') from None
    checkpoint(state)
    for attempt in range(3):
        read_result(candidate)
        if (candidate.get('publication_result') or {}).get('status') in ('sent','error'):
            break
        time.sleep(3)
    checkpoint(state)
    print(json.dumps(candidate,ensure_ascii=False,indent=2))
    if (candidate.get('publication_result') or {}).get('status')=='error':
        raise RuntimeError('Buffer reported publication failure; record preserved')

if __name__=='__main__':
    main()
