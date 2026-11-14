"""Read-only Buffer credential check. Never creates a post or logs a token."""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

QUERY = 'query CheckConnection { account { organizations { id } } }'


def validate_response(payload):
    if not isinstance(payload, dict) or payload.get('errors'):
        raise ValueError('Buffer APIがエラーを返しました。キーの権限・有効期限を確認してください。')
    account = (payload.get('data') or {}).get('account')
    if not isinstance(account, dict) or not account.get('organizations'):
        raise ValueError('Bufferアカウントの組織を確認できませんでした。')
    return len(account['organizations'])


def main():
    token = os.environ.get('BUFFER_API_KEY', '').strip().lstrip('\ufeff')
    if not token:
        print('失敗：GitHub SecretsにBUFFER_API_KEYがありません。', file=sys.stderr)
        return 1
    request = Request('https://api.buffer.com',
                      data=json.dumps({'query': QUERY}).encode('utf-8'),
                      headers={'Authorization': 'Bearer ' + token,
                               'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        validate_response(payload)
    except HTTPError as error:
        print(f'失敗：Buffer HTTP {error.code}。キーの有効期限・権限を確認してください。', file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError):
        print('失敗：Bufferとの通信に失敗しました。時間を置いて再実行してください。', file=sys.stderr)
        return 1
    except (ValueError, TypeError, AttributeError):
        # Do not print arbitrary remote error text, responses, headers or secrets.
        print('失敗：Bufferの認証結果を確認できませんでした。キー・権限を確認してください。', file=sys.stderr)
        return 1
    print('接続成功：GitHub ActionsからBufferのアカウントを読み取れました。')
    print('投稿・予約・削除は行っていません。Xへの投稿権限は別途確認が必要です。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
