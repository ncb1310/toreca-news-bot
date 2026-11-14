# トレカ女子速報 自動化

NCB公式ホームページとは別のトレカ専用リポジトリです。Python標準ライブラリのみ。

## 動作

- メーカー2サイトと販売店5サイトの計7系統を、日本時間8〜22時台の毎時17分・47分に確認。
- 初回は過去記事を基準として記録し、一切投稿しません。
- 2回目以降の新しい商品・販売告知だけが候補です。URL・タイトル・発表日で重複を防ぎます。
- 発表日から翌日まで。昨日の記事の「本日・明日」などは掲載しません。大会の抽選は対象外。
- 日本時間8時〜23時未満、1実行1件、1日最大10件。最新の公式タイトルと出典URLを掲載。
- 価格・販売店・在庫・受付期限は自動抽出・推測しません。本文全文や画像は転載しません。
- 実行結果はActionsの概要に表示。data/state.jsonに取得履歴・送信状況を保存。
- GitHub ActionsなのでPC停止中も実行可能ですが、定刻実行や配信を保証するものではありません。

## 有効化と停止

2026年11月15日（日本時間）から投稿を開始。`config.json` の `start_date_jst` で開始日を指定します。`posting_enabled` は初回検証時 false。公式ページ取得と対象Xチャンネルを検証後 true にすると、新着候補をBufferのshareNowで送信します。
対象チャンネルIDは `6af829a562b70b94b02a9277`。表示名・ID変更後もチャンネルIDで指定します。
停止は同ファイルをfalseへ戻すか、Actionsで **Toreca official news** をDisable workflow。

## 安全な送信記録

送信直前の sending 状態をGitHubへ保存できなければ送信しません。
API応答が不明なら uncertain とし、新たな投稿も停止します。再送は自動で行いません。
Buffer側で送信済みか確認してから該当状態をacceptedまたはignoredへ変更してください。
acceptedはBufferが受理した状態であり、Xへの公開完了を別途確認する必要があります。
取得失敗・robots制限・解析できないページを無理に迂回しません。
手動でdata/state.jsonを削除すると初回状態に戻るため、履歴は削除しないでください。

## 接続確認

Settings → Secrets and variables → Actions に `BUFFER_API_KEY` を登録済み。
Actionsの **Buffer connection check** はアカウントの読み取り確認だけです。
**Toreca official news** は対象Xチャンネルも確認します。
キー本体をコード・README・写真・Issueに貼らないでください。
キーの有効期限切れ・X接続切れは更新が必要です。パスワードは使いません。

## 現在の範囲

監視先の詳細と未対応先はSOURCES.mdを参照。店舗公式の新着記事を対象とし、受付中かどうか・応募締切は自動確定しません。相場、アフィリエイトリンク、返信は未対応。
掲載元の記事更新が少なければ投稿もありません。ワンピ公式の取得内容が古い場合は古い日付として記録し、投稿しません。
GitHubのスケジュールは遅延・未実行や、公開リポジトリの長期無活動による無効化があり得ます。Actionsで稼働を確認してください。

## 検証

```sh
python -m unittest discover -s tests -v
python news_bot.py
```

最後のコマンドはプレビューのみ。保存履歴も投稿も変更しません。
30件の単体テストと実ページHTMLによる解析を確認。
メーカー2サイトについてGitHub上でも公式ページ取得・履歴保存・対象Xチャンネルの読み取り確認が成功。追加先はカードラボ・ホビステ・ポケセン通販・古本市場の4サイトもクラウド取得成功。イオンはクラウドからの取得に失敗し保留。詳細は最新のActionsを参照。自動投稿は有効化済みで新着を待機しています。Bufferの投稿APIからXへの新着実配信はまだ未確認です。

## 公式資料

- https://developers.buffer.com/examples/create-text-post.html
- https://developers.buffer.com/examples/get-channel.html
- https://www.pokemon-card.com/info/
- https://www.onepiece-cardgame.com/topics/
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

Buffer API呼出しは対象チャンネルの確認を原則1日1回に抑え、送信直前は再確認します。10件投稿の場合は確認・作成で最大21呼出し/日が目安（手動操作や別ツールの使用分は別）。
