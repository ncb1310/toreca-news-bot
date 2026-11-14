# トレカ女子速報 自動化

トレカ専用。NCB公式ホームページとは別のリポジトリです。

## 現在できること

GitHub ActionsからBufferのAPIキーを使って、アカウントへの読み取り接続を確認します。
この段階では自動収集・投稿・予約・削除を行いません。

## 初回確認

1. Settings → Secrets and variables → Actions に `BUFFER_API_KEY` を登録。
2. 上部の Actions → **Buffer connection check** を開く。
3. 初回はファイル追加で自動実行。再試行は **Run workflow**。
4. 緑のチェックと `Read-only Buffer connection check` 内の「接続成功」を確認。

接続成功はBufferアカウントの読み取り確認です。対象Xチャンネルの投稿権限や、PC停止中の定期投稿を確認したことにはなりません。
キー本体をコード・README・Issue・写真に載せないでください。
有効期限切れの場合はBuffer側で更新してGitHubのSecretを入れ替えます。

## 次の構築段階

公式情報源の低頻度監視、過去記事の初回配信除外、重複防止、投稿上限、通信失敗時の再送重複防止を検証してから自動投稿を有効化します。
購入・抽選への代理応募は行いません。在庫・受付期限・価格を推測しません。

## ローカルテスト

Python 3.13、追加パッケージ不要。

```sh
python -m unittest discover -s tests -v
```

API仕様の出典： https://developers.buffer.com/guides/getting-started.html
