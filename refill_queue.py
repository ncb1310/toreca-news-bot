"""Keep eight verified, image-backed reservations ahead in Buffer per channel."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import news_bot as shared
import senran_bot as senran
import kingshot_bot as king
import editorial
from functools import lru_cache

ROOT=Path(__file__).resolve().parent
TARGET=8

def slots(account, now):
    hours=[8,12,18,22] if account=='senran1515' else [8,10,12,14,16,18,20,22]
    for offset in range(3):
        day=now.date()+timedelta(days=offset)
        for hour in hours:
            due=datetime.combine(day,datetime.min.time(),tzinfo=shared.JST).replace(hour=hour)
            if due>now+timedelta(minutes=15):
                yield due

def save(state,path):
    path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    shared.checkpoint(str(path.relative_to(ROOT)))

@lru_cache(maxsize=1)
def connected_channels():
    found=[]
    for org in shared.buffer_query('query { account { organizations { id } } }')['account']['organizations']:
        q='query { channels(input: { organizationId: '+json.dumps(org['id'])+' }) { id name service isQueuePaused } }'
        found.extend((org['id'],c) for c in shared.buffer_query(q)['channels'])
    return found

def channel_for(account):
    matches=[]
    matches=[(org,c) for org,c in connected_channels()
             if c['name'].lstrip('@').lower()==account and c['service']=='twitter']
    if len(matches)!=1 or matches[0][1].get('isQueuePaused'):
        raise RuntimeError('Exact channel unavailable or paused: '+account)
    return matches[0]

def queued(org,channel):
    q=('query { posts(first: 100, input: { organizationId: '+json.dumps(org)+
       ', filter: { status: [scheduled, sending], channelIds: ['+json.dumps(channel)+
       '] } }) { edges { node { id text dueAt status assets { mimeType source } } } pageInfo { hasNextPage } } }')
    result=shared.buffer_query(q)['posts']
    if result['pageInfo']['hasNextPage']:
        raise RuntimeError('Queue exceeds audit page; no new mutations')
    return [edge['node'] for edge in result['edges']]

MORNING_TOPICS = (
    ('poke-search-art', '今日は好きなイラストを1枚だけ選ぶなら、どのカードにしますか？🎨'),
    ('poke-first-hand', '初手がきれいにそろった日は、思わず写真を撮りたくなりますね📷'),
    ('lottery-calendar', '気になる抽選は、締切と当選発表をセットでメモ。朝のうちに見ると安心です🗓️'),
    ('one-counter', '最後まで手札に残して助かったカウンター、みんなは覚えてますか？🃏'),
    ('poke-bench', '最初のベンチにどの子を出すか。対戦はあの瞬間から楽しいですよね🌱'),
    ('lottery-result', '当選メールを待つ日は、つい受信箱を何度も開いちゃいますね📬'),
    ('poke-evolution', '進化先ばかり手札に集合。肝心のたねポケモン、今日は来てくれるかな？🌱'),
)


def toreca_morning(history, due):
    day = due.date()
    key = 'toreca-morning-' + day.isoformat()
    if key in history:
        return None
    guide_id, message = MORNING_TOPICS[day.weekday()]
    artwork = next((p['image_url'] for p in history.values()
                    if p.get('guide_id') == guide_id and p.get('image_url')), None)
    if not artwork:
        raise RuntimeError('Missing Toreca morning artwork: ' + guide_id)
    return {'key': key, 'kind': 'morning', 'image_url': artwork,
            'text': 'おはようございます☀️\\n' + message + '\\n#トレカ #トレカ女子'}


def refill(account):
    now=datetime.now(shared.JST)
    module=senran if account=='senran1515' else (shared if account=='toreca_joshi' else king)
    path=ROOT/('data/senran-state.json' if module==senran else ('data/state.json' if module==shared else 'data/kingshot-state.json'))
    state=json.loads(path.read_text()) if path.exists() else {'posts':{}}
    history=state.setdefault('editorial_posts' if module==shared else 'posts',{})
    org,channel=channel_for(account)
    current=queued(org,channel['id'])
    if any(p.get('status') in ('sending','uncertain') for p in (editorial.records(state) if module==shared else history.values())):
        raise RuntimeError('Uncertain previous send; review before reserving more')
    # Reconcile outcomes, including lost/deleted reservations, without resending.
    pending=[item for item in history.values() if item.get('scheduled_at') and item.get('post_id')
             and datetime.fromisoformat(item['scheduled_at'])<=now
             and (item.get('publication_result') or {}).get('status') not in ('sent','error')]
    if pending:
        fields='id status sentAt externalLink assets { mimeType source }'
        q='query { '+' '.join('p'+str(i)+': post(input: { id: '+json.dumps(p['post_id'])+' }) { '+fields+' }' for i,p in enumerate(pending))+' }'
        results=shared.buffer_query(q)
        for i,item in enumerate(pending):
            item['publication_result']=results.get('p'+str(i))
    save(state,path)
    config={} if module==senran else json.loads((ROOT/('config.json' if module==shared else 'kingshot-config.json')).read_text())
    if module==shared and channel['id']!=config['channel_id']:
        raise RuntimeError('Toreca channel does not match configured account')
    planned = list(slots(account, now))
    if module == shared:
        planned.sort(key=lambda due: (due.hour != 8, due))
    for due in planned:
        if len(current)>=TARGET:
            break
        if any(p.get('dueAt') and abs((datetime.fromisoformat(p['dueAt'].replace('Z','+00:00'))-due).total_seconds())<2700 for p in current):
            continue
        # Selection runs at the planned publication time. Previous reservations
        # count for topic, image, daily-limit and duplicate checks.
        state['last_checked_at']=due.isoformat()
        if module==senran:
            candidate=senran.select(state,due)
        elif module==shared:
            candidate=(toreca_morning(history, due) if due.hour == 8 else editorial.select_fallback(state,{},due,config))
        else:
            candidate=king.select(state,[],due,config)
        if not candidate:
            continue
        if module==shared and candidate.get("kind") != "morning":
            history[candidate['key']]=candidate
            try:
                shared.official_page(candidate['url'])
            except Exception as exc:
                candidate.update(status='verification_failed',verification_failed_date=due.date().isoformat(),verification_error=type(exc).__name__)
                save(state,path)
                continue
            shared.publish_card(candidate,due)
            candidate['text']=shared.format_post(candidate)
        candidate['image_url']=king.verified_image(candidate,state,config,due)
        candidate.update(status='sending',attempt_date=due.date().isoformat(),
                         attempted_at=now.isoformat(),scheduled_at=due.isoformat())
        history[candidate['key']]=candidate
        save(state,path)
        stamp=due.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        query=('mutation { createPost(input: { text: '+json.dumps(candidate['text'])+
               ', channelId: '+json.dumps(channel['id'])+', schedulingType: automatic, mode: customScheduled, dueAt: '+
               json.dumps(stamp)+', assets: [{image: {url: '+json.dumps(candidate['image_url'])+
               '}}], needsApproval: false }) { ... on PostActionSuccess { post { id status dueAt text assets { mimeType source } } } ... on MutationError { message } } }')
        try:
            result=shared.buffer_query(query).get('createPost',{})
            post=result.get('post')
            if not post or not post.get('id'):
                # An explicit rejection confirms no reservation was accepted.
                if result.get('message'):
                    candidate.update(status='rejected',error=result['message'])
                    save(state,path)
                    raise ValueError('Buffer rejected reservation: '+result['message'])
                raise RuntimeError('Unconfirmed reservation')
            candidate.update(status='accepted',post_id=post['id'],publication_result=post)
            if module==shared:
                candidate['buffer_post_id']=post['id']
        except ValueError:
            raise
        except Exception:
            candidate['status']='uncertain'
            save(state,path)
            raise RuntimeError('Reservation outcome uncertain; no automatic resend') from None
        save(state,path)
        current.append(post)
    actual=current
    state['last_checked_at']=datetime.now(shared.JST).isoformat()
    state['last_reservation_check']={'checked_at':now.isoformat(),'queued':len(actual),
        'target':TARGET,'posts':actual,'shortfall':max(0,TARGET-len(actual))}
    save(state,path)
    print(json.dumps({'account':account,**state['last_reservation_check']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Live reservations require durable workflow checkpoints')
    failed=[]
    for account in ('senran1515','kingshot5555','toreca_joshi'):
        try:
            refill(account)
        except Exception as exc:
            print(account,type(exc).__name__,str(exc))
            failed.append(account)
            if isinstance(exc,shared.BufferRateLimit):
                break
    if failed:
        raise RuntimeError('Reservation refill failed: '+', '.join(failed))
