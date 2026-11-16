"""Keep eight verified, image-backed reservations ahead in Buffer per channel."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import news_bot as shared
import senran_bot as senran
import kingshot_bot as king

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

def channel_for(account):
    matches=[]
    for org in shared.buffer_query('query { account { organizations { id } } }')['account']['organizations']:
        q='query { channels(input: { organizationId: '+json.dumps(org['id'])+' }) { id name service isQueuePaused } }'
        matches.extend((org['id'],c) for c in shared.buffer_query(q)['channels']
                       if c['name'].lstrip('@').lower()==account and c['service']=='twitter')
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

def refill(account):
    now=datetime.now(shared.JST)
    module=senran if account=='senran1515' else king
    path=ROOT/('data/senran-state.json' if module==senran else 'data/kingshot-state.json')
    state=json.loads(path.read_text()) if path.exists() else {'posts':{}}
    org,channel=channel_for(account)
    current=queued(org,channel['id'])
    if any(p.get('status') in ('sending','uncertain') for p in state['posts'].values()):
        raise RuntimeError('Uncertain previous send; review before reserving more')
    # Reconcile outcomes, including lost/deleted reservations, without resending.
    for item in state['posts'].values():
        if item.get('scheduled_at') and item.get('post_id'):
            king.read_result(item)
    save(state,path)
    config={} if module==senran else json.loads((ROOT/'kingshot-config.json').read_text())
    for due in slots(account,now):
        if len(current)>=TARGET:
            break
        if any(p.get('dueAt') and abs((datetime.fromisoformat(p['dueAt'].replace('Z','+00:00'))-due).total_seconds())<2700 for p in current):
            continue
        # Selection runs at the planned publication time. Previous reservations
        # count for topic, image, daily-limit and duplicate checks.
        state['last_checked_at']=due.isoformat()
        if module==senran:
            candidate=senran.select(state,due)
        else:
            candidate=king.select(state,[],due,config)
        if not candidate:
            continue
        candidate['image_url']=king.verified_image(candidate,state,config,due)
        candidate.update(status='sending',attempt_date=due.date().isoformat(),
                         attempted_at=now.isoformat(),scheduled_at=due.isoformat())
        state['posts'][candidate['key']]=candidate
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
        except ValueError:
            raise
        except Exception:
            candidate['status']='uncertain'
            save(state,path)
            raise RuntimeError('Reservation outcome uncertain; no automatic resend') from None
        save(state,path)
        current.append(post)
    actual=queued(org,channel['id'])
    state['last_checked_at']=datetime.now(shared.JST).isoformat()
    state['last_reservation_check']={'checked_at':now.isoformat(),'queued':len(actual),
        'target':TARGET,'posts':actual,'shortfall':max(0,TARGET-len(actual))}
    save(state,path)
    print(json.dumps({'account':account,**state['last_reservation_check']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Live reservations require durable workflow checkpoints')
    failed=[]
    for account in ('senran1515','kingshot5555'):
        try:
            refill(account)
        except Exception as exc:
            print(account,type(exc).__name__,str(exc))
            failed.append(account)
    if failed:
        raise RuntimeError('Reservation refill failed: '+', '.join(failed))
