# トレカ女子ちゃん 自動投稿

X `@toreca_joshi` 専用。GitHub Actions → Buffer → Xで動作するので、PCやチャットを開いておく必要はありません。

## 自動運用

- 日本時間8〜22時台、毎時17分・47分に収集。GitHubによる遅延があります。
- メーカー2サイト・販売店5サイトを確認し、取得成功した情報源だけを使用。
- 新しい商品・予約・抽選・再販の告知を優先します。大会の抽選は除外。
- 新着がない場合は、直近30日以内のメーカー商品告知から商品紹介を選びます。過去の抽選・予約告知を受付中として流しません。
- 商品紹介もなければ、24種類の確認メモ・初心者向け解説から選びます。同じ解説・同じ商品URLは14日間繰り返しません。解説は1日4件まで。
- 投稿前に出典ページの取得可否を再確認。確認できない候補はその日は除外。
- 1日10件を目安に時間帯へ分散。新着を含め最大15件、原則55分以上の間隔を空けます。
- 候補切れ・出典障害・重複制限時は本数が減ります。10件を保証する仕組みではありません。

## 全投稿に専用画像

`post_cards.py` が、各投稿の見出し・発表日・出典・店舗名、または3つの解説ポイントを1200×1200のPNGにします。
共通の案内画像へフォールバックしません。画像を生成・公開・取得確認できなければ投稿しません。
画像は `assets/generated/` に保存し、その画像を含むコミットの固定URLをBufferへ渡します。
本文にも出典リンクを付け、公式アカウントと誤認させない表示を画像に入れます。

## 記録と重複防止

`data/state.json` にニュース履歴・解説履歴・投稿前の送信予定を記録します。
GitHubへの保存に失敗した場合は送信しません。Bufferの応答が不明なら `uncertain` とし、それ以降の送信も停止します。
`accepted` はBuffer受理です。Xの公開完了は `publication_result.status = sent`、公開URL・時刻・添付画像で別途確認します。
公開状態は送信直後と後続の実行で読み取り、各投稿最大6回まで記録。再送はしません。

## 設定と停止

`config.json` の `posting_enabled: false` で停止。`editorial_enabled: false` で新着速報のみに戻せます。
`daily_target`、`max_posts_per_day`、`editorial_max_per_day`、`min_post_interval_minutes` で本数と間隔を設定します。
対象チャンネルIDは `6af829a562b70b94b02a9277`。Xのパスワードは使いません。
GitHub Actions Secret `BUFFER_API_KEY` を利用。キーをコードやログへ出力しません。

## 検証

Python 3.13、Pillow 13.0.0、Noto Sans CJKを使用。

```sh
python -m pip install Pillow==13.0.0
python -m unittest discover -s tests -v
python news_bot.py
```

最後のコマンドはプレビューのみ。公開・履歴保存は行いません。
`--live` はGitHub Actions内だけで有効です。`Toreca official news` の実行概要と `report.json` で状態を確認できます。

情報源の詳細・取得制限はSOURCES.mdを参照。受付期限や応募条件の自動確定、価格相場の収集、アフィリエイト、返信は未実装です。
