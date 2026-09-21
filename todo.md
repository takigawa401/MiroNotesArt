# 開発タスク（TDD）

上から順に、pytestで失敗（Red）→最小実装で成功（Green）→整理（Refactor）を実施する。
実接続は行わず、外部通信を禁止したテストとAPIモックで検証する。

- [x] 既存構成・Miro公式REST仕様・16色の参照先・OAuth・レート制限を確認
- [x] 1. パレット、sRGB→CIELAB（D65）、ΔE76、同点時の決定性
- [x] 2. JPG検証・EXIF回転・RGB変換・BOX縮小・枚数上限・配置計算
- [x] 3. RESTペイロード・逐次通信・429待機と上限・認証エラー・結果不明
- [x] 4. 原子的な状態保存・一致検証・成功済みのスキップ・結果不明の再開停止
- [x] 5. CLI・.env・プレビューPNG/JSON・dry-run・進捗・不正入力
- [x] 6. 不明結果の手動確認反映・中断/保存失敗・多重起動対策
- [x] 7. 日本語README・依存定義・VS Code・.gitignore・GitHub CI
- [x] 8. 全テスト・実JPGでのdry-run・成果物確認・未検証事項の報告
- [x] 9. 最終レビューで見つかった境界値: トークンの制御文字・非ASCII文字を送信前に拒否
- [x] 10. 最終レビューで見つかった境界値: 数値が同じ既定値と明示指定で再開できること

## 仕様確認（2026-09-21）

- REST: https://developers.miro.com/reference/create-sticky-note-item-1
- 色見本のリンク元: https://developers.miro.com/docs/websdk-reference-sticky-note
- レート制限: https://developers.miro.com/reference/rate-limiting
- OAuth: https://developers.miro.com/docs/getting-started-with-oauth

## TDD実行記録

各サイクルの確認結果を追記する。

- 1: `test_colors.py` がモジュール未実装で失敗 → 実装後21件成功。
  色定義を不変データに分離し、Lab変換のキャッシュを追加。
- 2: `test_mosaic.py` が未実装で失敗 → 色変換と合わせ44件成功。
  設定検証と画像処理を分離。列数からの四捨五入は整数演算に整理。
- 3: `test_api.py` が未実装で失敗 → 23件成功。
  待機情報の解析を独立関数へ整理。通信例外・レスポンス本文はログに出さない。
- 4: `test_state.py` が未実装で失敗 → 13件成功。
  計画のSHA-256整合性検証と状態遷移を別モジュールに分離。
- 5: `test_cli.py` が未実装で失敗 → 14件成功。
  純粋な赤(255,0,0)とMiroのredは異なるため、色別枚数のテスト画像を
  パレットのredに修正。PNG/JSONを同じ配置データから作る処理に整理。
- 6: `test_recovery.py` が未実装で失敗 → CLIと合わせ27件成功、全体107件成功。
  ロックをコンテキストマネージャーにし、確認操作と送信を共通のロック内へ整理。
- 9: トークン境界値の3テストが失敗 → 送信前の検証追加で3件成功。
- 10: 既定の200と明示指定200.0の再開テストで不一致エラーを確認。
  設定の浮動小数点項目を生成時に正規化し、型の表現差を解消。
  対象テスト1件が成功。

## 最終検証（2026-09-21）

- Windows / Python 3.11.4、専用`.venv`へのeditableインストール成功。
- Pillow 12.3.0 / requests 2.34.2 / python-dotenv 1.2.3 / pytest 9.1.1。
- `python -m pytest -q`: **111 passed**。
- `python -m ruff check .`: 成功。
- `python -m ruff format --check .`: 成功。
- `python -m pip check`: 依存関係の不整合なし。
- 生成した320×200のJPGから40×25（1,000枚）の配置JSONと640×400のPNGを生成。
  PNGを目視確認し、JSONの先頭/末尾座標、16色定義、dry-runでstate.jsonがないことを確認。
- `.env`、入力画像、カスタム出力先の状態ファイル、`.venv`のGit除外を確認。
  `.env.example`は除外されないことを確認。
- Miro実接続・実画面・GitHubへのpush/CIは実行していない。
  ご自身での接続方法、少数での確認方法、残る制約をREADMEに記載。

## 利用者による動作確認

- 実Miroボードへの書き出し成功の報告を受領。READMEの検証状況に反映。
- 初回コミット前にpytest 111件とRuffの静的・整形チェックの成功を再確認。
