# Miro Sticky Art

ローカルのJPG/JPEG画像を16色のモザイクに変換し、`gray`以外のマスにつき
正方形の付箋1枚をMiroボードに配置するPython CLIです。
`gray`のマスには何も貼らず、その位置を空けます。背景の明るい画像などで付箋枚数を減らし、
同じ枚数上限でも、より多い列数を選べるようにします。
画像処理はPillow、通信はrequests、UNITテストはpytestを使用します。

## Windows / VS Codeでのセットアップ

Python 3.11以上を用意し、VS Codeでこのプロジェクトのフォルダーを開きます。
以下はプロジェクト直下のPowerShellで実行してください。

```powershell
cd C:\Python\MiroNotesArt
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

`py`がない場合は`python -m venv .venv`を使います。
PowerShellの実行ポリシーでActivate.ps1が実行できない場合は、ポリシーを変更せず、
各コマンドの`python`を`.\.venv\Scripts\python.exe`に置き換えてください。

VS Codeの拡張機能「Python」をインストールし、コマンドパレットの
`Python: Select Interpreter`で`.venv\Scripts\python.exe`を選びます。
同梱のF5デバッグ設定はプレビューのみを生成します。テストはTestingパネルでも実行できます。

## まずプレビューを作る（Miro認証不要）

画像を`images`フォルダーへ置きます。手元に画像がなければ、次のコマンドで
動作確認用のグラデーションJPGを生成できます。既存ファイルは上書きしません。

```powershell
python tools/make_sample.py
python -m miro_sticky_art --image "./images/sample.jpg" --columns 40 --dry-run
```

`output/<UTC日時>-<実行ID>/`に次を保存し、列数・行数・総マス数・gray除外数・
作成予定枚数・作成する付箋の色別枚数を表示します。

| ファイル | 内容 |
| --- | --- |
| `preview.png` | grayの場所が透明なRGBAプレビュー。最近傍補間で整数倍に拡大 |
| `layout.json` | 画像のSHA-256、設定、パレット、除外方針。`cells`に空白を含む全マスと`action`、`notes`に作成対象のみを記録 |
| `state.json` | 実送信時のみ。非grayの作成済みID・元の行列・状態・手動確認履歴 |

**透明PNGはPCで確認するための画像です。Miroへ画像を貼り付けることはありません。**
透明部分は画像ビューアで市松模様などに見えることがあります。
実ボードでは空白にした場所の背景や、既にあるオブジェクトがそのまま見えます。
全マスgrayの場合、通常実行でも認証不要で0枚として正常終了し、PNG/JSONだけを保存します。
APIクライアントや新規state.jsonは作りません。

実行ごとに別フォルダーを作り、以前の記録を上書きしません。
`--output-dir "./art-output"`で保存先を変更できます。
プレビューには付箋の影や間隔は描きません。最大16倍、長辺が概ね2048px以下となる
整数倍率で拡大します。元の格子が2048を超える場合は縮小せず1倍です。

## Miroアプリと取得済みトークンの準備

このCLIはOAuthブラウザー認証・トークンの自動更新を実装せず、取得済みトークンを使います。
以下のMiro画面の操作はご自身のアカウントで行ってください。

1. Miroへログインし、[Your apps](https://miro.com/app/settings/user-profile/apps)から
   **Create new app**を選びます。必要に応じてDeveloper teamを作成します。
2. アプリのPermissionsで **`boards:write`** を有効にして保存します。
   対象ボードの閲覧・編集権限を持つユーザーで操作してください。
3. **Install app and get OAuth token**を開き、対象ボードが属するチームを選び、
   **Install & authorize**を実行します。チームのポリシーによって管理者の許可が必要です。
4. 発行されたアクセストークンをローカルの`.env`へ設定します。
   トークンをチャットやGitHubへ送る必要はありません。
5. 対象ボードのURLが`https://miro.com/app/board/uXjEXAMPLE=/`なら、
   `/board/`の直後から次の`/`までの`uXjEXAMPLE=`がボードIDです。
   `=`を省略せず、URL全体ではなくIDだけを設定してください。

```dotenv
MIRO_ACCESS_TOKEN=取得した値をローカルだけに入力
MIRO_BOARD_ID=対象ボードのID
```

優先順位は、ボードIDが`--board-id` → 環境変数 → カレントディレクトリの`.env`、
トークンが環境変数 → `.env`です。既に設定された空の環境変数も`.env`より優先します。
`.env`の変数展開は無効です。トークンをコマンド引数には受け付けません。

公式手順:
[アプリ作成・インストール](https://developers.miro.com/docs/rest-api-build-your-first-hello-world-app)、
[OAuthガイド](https://developers.miro.com/docs/getting-started-with-oauth)。

### 期限切れになった場合

401で停止したら、同じアプリ・チームの有効なトークンを取得し、`.env`または環境変数を
更新して、後述の`--resume`で再開します。トークンの変更は再開の一致確認に影響しません。

有効期限付きOAuthでは、[公式OAuthガイドのStep 4](https://developers.miro.com/docs/getting-started-with-oauth)
に従い、`POST https://api.miro.com/v1/oauth/token`に`grant_type=refresh_token`、
`client_id`、`client_secret`、現在の`refresh_token`を送信して更新します。
返却された新しいアクセストークンとリフレッシュトークンを両方保管し、古いものと入れ替えます。
有効期限は応答の`expires_in`を確認してください。CLIはこれらの更新用秘密情報を保存しません。
リフレッシュトークンがない、期限切れ、または失効している場合は再度インストール・認可を行います。
認可コード方式では同ガイドのStep 1～2に従い、設定済みのredirect URIで受け取ったコードを
`grant_type=authorization_code`で交換してください。

## Miroへの配置

まず`--dry-run`で枚数とPNGを確認し、同じ画像・設定で実行します。
実送信コマンドは確認プロンプトなしでボードを変更します。

```powershell
python -m miro_sticky_art --image "./images/sample.jpg" --board-id "BOARD_ID" --columns 40
```

`.env`にボードIDを設定した場合は`--board-id`を省略できます。
最初の実接続確認には、空のテスト用ボードへ`--columns 2`で少数を作成してください。
列数を変えて再度通常実行すると別の作品を作成するため、既存作品と重ねない座標を指定します。

```powershell
python -m miro_sticky_art --image "./images/sample.jpg" --columns 20 --note-size 200 --gap 5 --origin-x 5000 --origin-y 0 --interval 0.2
```

| オプション | 既定値 | 意味 |
| --- | --- | --- |
| `--image` | 必須 | JPG/JPEGファイル |
| `--board-id` | 環境変数 / `.env` | ボードID。dry-runでは不要 |
| `--columns` | 40 | 横方向のマス数、1以上の整数 |
| `--note-size` | 200 | 正方形付箋の幅、0より大きい有限値 |
| `--gap` | 0 | 間隔、0以上の有限値 |
| `--origin-x`, `--origin-y` | 0, 0 | 左上の付箋の中心。負の座標も可 |
| `--max-notes` | 2500 | gray除外後の作成枚数上限、1以上の整数 |
| `--dry-run` | 無効 | API呼び出しなし。PNGとJSONのみ |
| `--output-dir` | `output` | 新規実行フォルダーの親ディレクトリ |
| `--interval` | 0.1 | HTTP応答後、次の送信までの最小待機秒数 |
| `--max-retries` | 5 | 429のみ再試行する回数。初回を含め最大6回 |
| `--timeout` | 30 | 読み取りタイムアウト秒数。接続はこれと10秒の小さい方 |
| `--resume` | なし | 再開する`state.json`のパス |
| `--resolve-created` | なし | `行,列=ID`。結果不明を作成済みに記録するだけ |
| `--resolve-absent` | なし | `行,列`。未作成を目視等で確認した結果を記録するだけ |

作成枚数の上限は**16色への変換とgray除外の後**に検査します。
全マス数が2,500を超えていても、非grayが2,500枚以下なら送信できます。
超過時はdry-runでもAPI送信・新規成果物保存を行わず停止します。
2,500枚はこのツールの既定値です。除外後も多すぎる場合は`--columns`を小さくしてください。
上限を増やす場合は処理時間とボード負荷に注意してください。

大量のマスによるローカル処理の負荷を抑えるため、別途、総マス数を**1,000,000マスまで**に
制限します。この処理用上限は画像の展開・縮小前に検査し、`--max-notes`を増やしても変更されません。

例えば、ある画像を100列にした場合の表示は次のようになります。

```text
100列 × 67行、総マス数: 6,700
gray除外: 5,174マス、作成予定: 1,526枚
```

効果は画像に含まれるgrayの割合によります。列数によって領域の平均色も変わるため、
同じ割合で減るとは限らず、大きな`--columns`で必ず上限内に収まるという保証はありません。

## 途中停止と再開

最初の送信前に表示される`state.json`のパスを保管してください。
同じ画像・ボードID・すべての画像/配置/通信設定を指定して再開します。
既定値以外を指定した項目は、再開時にも同じ値を指定してください。

```powershell
python -m miro_sticky_art --image "./images/sample.jpg" --board-id "BOARD_ID" --columns 40 --resume "./output/実行フォルダー/state.json"
```

- 画像のSHA-256・寸法・設定・ボードID・パレット・配置内容の一致を確認します。
  画像のパスやファイル名だけの変更は可能です。送信間隔や上限も一致確認の対象です。
- 作成済みの付箋IDを持つマスは再送しません。完了した記録を再開しても追加作成しません。
- 進捗の分母と`--max-notes`は非grayの作成予定総数です。再開時も作成済みを含めて判定します。
  記録の行・列は元画像の格子に対応するため、grayの位置には欠番があります。
- 再開時の保存先は`state.json`と同じフォルダーです。`--output-dir`は使いません。
- `--resume`なしの実行は新しい作品です。同じボードへ繰り返すと重複するので、再開には必ず記録を指定します。
- `--dry-run`は`state.json`を作りません。dry-runと再開は同時指定できません。

### gray除外に対応する前の記録を再開する場合

本変更では、配置計画の`plan_version`と状態の`schema_version`を`2`にしています。
`skip_colors: ["gray"]`も整合性検証の対象です。全マスの`cells`はlayout.jsonに保存し、
送信ごとに書き換えるstate.jsonには作成対象だけを保持します。

旧形式（`schema_version: 1`）は自動変換せず、状態を変更せずにエラーで停止します。
途中の実行がある場合は、更新前のコードで完了させてください。
既に更新した場合は、現在の作業を残したまま、初回版を別フォルダーへ展開できます。

```powershell
git worktree add --detach ..\MiroNotesArt-v1 9c7aae9
```

旧フォルダーで仮想環境と依存関係をセットアップし、元の認証情報と設定を用意して、
入力画像とstate.jsonを**元の場所の絶対パス**で指定します。
以下の`元の実行フォルダー`を置き換え、既定値以外の設定は元の実行に合わせてください。

```powershell
cd ..\MiroNotesArt-v1
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
# この旧フォルダーの.envに、元の実行と同じボードIDと有効なトークンを設定
.\.venv\Scripts\python.exe -m miro_sticky_art --image "C:\Python\MiroNotesArt\images\sample.jpg" --columns 40 --resume "C:\Python\MiroNotesArt\output\元の実行フォルダー\state.json"
```

旧stateの削除や、同じ座標への新規実行で再開を代用しないでください。
既に作成したgray付箋を自動で削除する機能はありません。

### 「結果不明」がある場合

タイムアウト・接続切断・5xx・408・想定外の応答・成功IDの欠落は、作成済みの可能性があります。
自動では再送せず`unknown`として保存し、再開も停止します。
送信前に`in_flight`を保存するので、強制終了や成功後の保存失敗も、次回は結果不明として扱います。
429の待機中など、実際には作成されていない中断でも保守的に確認を要求する場合があります。

1. `state.json`で`unknown`の行・列（**0始まり**）を調べ、同ファイルの`plan.notes`または
   `layout.json`で対応する色・中心座標を確認します。
2. 対象Miroボードを開き、該当位置の付箋の存在・色・幅を確認します。
   付箋を選択して **Copy link** を使うと、リンクの`moveToWidget`からIDを確認できます。
   判断できない場合は再送せず、そのまま保留してください。
3. 存在する場合、確認した付箋IDを記録します（このコマンドはAPIを呼びません）。

```powershell
python -m miro_sticky_art --image "./images/sample.jpg" --board-id "BOARD_ID" --columns 40 --resume "./output/実行フォルダー/state.json" --resolve-created "0,3=確認した付箋ID"
```

4. ボード上に存在しないと確認できた場合だけ、未作成に戻します（まだAPIは呼びません）。

```powershell
python -m miro_sticky_art --image "./images/sample.jpg" --board-id "BOARD_ID" --columns 40 --resume "./output/実行フォルダー/state.json" --resolve-absent "0,3"
```

5. 全件を確認したら、確認用オプションを外した`--resume`コマンドで続行します。
   確認コマンド自体にはトークンは不要ですが、ボードIDと設定の一致は必要です。

このCLIはMiroの読み取りAPIを実装していません。APIで照合したい場合はアプリに
`boards:read`を追加して再認可し、[Get items](https://developers.miro.com/reference/get-items-1)
等で`type=sticky_note`とページネーションを使い、位置・色・IDを確認できます。
通常の作成だけなら`boards:write`で足ります。

### 多重実行・強制終了

同じ実行フォルダーでは`.run.lock`により同時送信を禁止します。
強制終了で残った場合、ファイル内の`pid`をWindowsタスクマネージャー等で確認し、
そのPythonプロセスが停止したことを確かめてから、その実行フォルダーの`.run.lock`だけを削除してください。
状態ファイルは削除しないでください。別フォルダーや別マシンからの重複実行は検出できません。

## 画像・色・配置の仕様

EXIFの向き（反転を含む）を補正してRGBに変換し、横を指定列数、縦を
`max(1, floor(元の高さ × 列数 / 元の幅 + 0.5))`にします。
整数格子のため縦横比には丸め誤差があります。BOXフィルターによる領域平均相当の縮小後、
sRGBをD65白色点のCIELABへ変換し、ΔE76が最小の色を選びます。
同点では下表の先頭を優先します。ディザリングは行いません。

色変換後に`gray`と判定されたマスだけを作成対象から除きます。
16色の候補からgrayを外すことや、元画像に白色の閾値を適用する処理は行いません。
画像内部のgrayも空白になります。除外した場所を詰めたり、周囲の余白を切り取ったりせず、
元の格子寸法と行・列・中心座標を維持します。

色名はREST APIへ送るenum、HEX/RGBは色比較とプレビューのための参照値です。
**RGBはMiroの実画面の測色値やREST APIが保証する値ではありません。**
2026-09-21に[公式Web SDK付箋仕様のfillColor](https://developers.miro.com/docs/websdk-reference-sticky-note)
が参照する色見本のリンク先から確認しました。一般的な同名色やShapeのパレットとは異なります。
RESTの16色enumは[付箋作成API](https://developers.miro.com/reference/create-sticky-note-item-1)
の公開スキーマでも確認しています。

| API色名 | HEX（公式資料の色見本リンク先） | RGB |
| --- | --- | --- |
| gray | [#f5f6f8](https://www.color-hex.com/color/f5f6f8) | 245, 246, 248 |
| light_yellow | [#fff9b1](https://www.color-hex.com/color/fff9b1) | 255, 249, 177 |
| yellow | [#f5d128](https://www.color-hex.com/color/f5d128) | 245, 209, 40 |
| orange | [#ff9d48](https://www.color-hex.com/color/ff9d48) | 255, 157, 72 |
| light_green | [#d5f692](https://www.color-hex.com/color/d5f692) | 213, 246, 146 |
| green | [#c9df56](https://www.color-hex.com/color/c9df56) | 201, 223, 86 |
| dark_green | [#93d275](https://www.color-hex.com/color/93d275) | 147, 210, 117 |
| cyan | [#67c6c0](https://www.color-hex.com/color/67c6c0) | 103, 198, 192 |
| light_pink | [#ffcee0](https://www.color-hex.com/color/ffcee0) | 255, 206, 224 |
| pink | [#ea94bb](https://www.color-hex.com/color/ea94bb) | 234, 148, 187 |
| violet | [#c6a2d2](https://www.color-hex.com/color/c6a2d2) | 198, 162, 210 |
| red | [#f0939d](https://www.color-hex.com/color/f0939d) | 240, 147, 157 |
| light_blue | [#a6ccf5](https://www.color-hex.com/color/a6ccf5) | 166, 204, 245 |
| blue | [#6cd8fa](https://www.color-hex.com/color/6cd8fa) | 108, 216, 250 |
| dark_blue | [#9ea9ff](https://www.color-hex.com/color/9ea9ff) | 158, 169, 255 |
| black | [#000000](https://www.color-hex.com/color/000000) | 0, 0, 0 |

付箋は`data.shape="square"`、`data.content=""`、`style.fillColor=色名`、
`geometry.width=note_size`で作成します。高さは送信しません。
左上の中心を開始座標として、行単位で次の座標へ配置します。

```text
x = origin_x + col * (note_size + gap)
y = origin_y + row * (note_size + gap)
```

ボード単位で右が+X、下が+Yです。Miro固有の影・縁・選択表示・ズームや画面の色管理により
プレビューと実画面は異なります。特に正方形の紙面でも影を含む外形の高さは幅と異なり、
`gap=0`では影の重なり等が見えます。
ICCプロファイルの色管理は行わず、RGB変換後をsRGBと仮定します。厳密な色管理が必要なら
あらかじめsRGBのJPEGへ変換してください。指定列数が画像の幅より大きい場合は拡大します。

## 通信とエラー

逐次送信で進捗`作成済み N/gray除外後の総数 枚`を表示します。
429では指数バックオフ（1, 2, 4, …、最大64秒）と`Retry-After`（秒またはHTTP日時）、
`X-RateLimit-Reset`（UNIX秒）のうち最も遅い時刻まで待機します。
サーバーの待機指示は64秒で切り詰めません。残クレジットが付箋作成1件のコスト未満なら、
成功後でも次の送信をResetまで待ちます。ヘッダーが不正ならバックオフへフォールバックします。
タイムアウトは接続／読み取り用であり、実行全体の制限時間ではありません。

[公式レート制限](https://developers.miro.com/reference/rate-limiting)によると、確認時点で
付箋作成はLevel 2（100 credits）、ユーザーとアプリの組み合わせに対し
全体100,000 credits/分です。制限は変更され得るため、固定の理論値だけには依存しません。
401・403・400等は原因と確認箇所を表示して停止し、自動再試行しません。
レスポンス本文やrequestsの例外本文は、認証情報の混入を避けるため出力・保存しません。

企業プロキシ等でTLS証明書エラーになる場合は、管理者から提供されたCA証明書を
`REQUESTS_CA_BUNDLE`で設定してください。証明書検証を無効にする機能はありません。

終了コード: `0`成功、`2`入力/設定/API拒否/再開条件のエラー、`3`結果不明、`130`Ctrl+C。

## テストと開発

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

TDDのタスクリストとRed→Green→Refactorの実行記録は[todo.md](todo.md)にあります。
pytestは外部通信を禁止し、画像はテスト中に生成、APIはモック化しています。
縦横比・EXIF・平均色・CIELAB・16色・2×2配置・dry-run・不正入力・429・認証エラー・
結果不明・再開・保存失敗・多重起動を検証します。
gray混在時の座標維持、透明PNG、JSONの全マス記録、除外後の上限、全grayの0枚終了、
欠番のある行列での再開、旧形式の拒否もテストします。

```text
miro_sticky_art/
  config.py       設定と数値検証
  palette.py      API色名と色見本のHEX/RGB
  colors.py       CIELABとΔE76
  imaging.py      JPG読み込み、EXIF、BOX縮小、画像識別
  layout.py       行列と座標
  artifacts.py    PNGとJSON
  api.py          REST通信、レート制限、結果不明の分類
  state.py        状態保存、一致検証、手動確認履歴
  locking.py      同時実行ロック
  runner.py       保存と逐次送信の調停
  cli.py          引数、.env、表示、終了コード
tests/           pytestのUNIT/CLI結合テスト
tools/           サンプルJPGの生成
.vscode/         Windows向けデバッグ・テスト設定
.github/workflows/  GitHub Actions
```

## GitHubでの管理

`.env`、入力画像、プレビュー、ボードIDや作成済みIDを含む実行記録、仮想環境は
`.gitignore`で除外しています。依存関係は`pyproject.toml`で管理しています。
独自のログや出力名を追加した場合は、共有前に除外設定を確認してください。

GitHubへの接続とpushはご自身で行ってください。VS Codeの「ソース管理」から
GitHubへサインインしてリポジトリを公開するか、次の手順を使います。

```powershell
git init
git status --short
git add .
git diff --cached --stat
git commit -m "Implement Miro sticky note art CLI"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPOSITORY.git
git push -u origin main
```

既にGit管理済みなら`git init`は不要です。`origin`がある場合は`git remote -v`で確認し、
`remote add`は省略してください。GitHub上に既存コミットがある場合は、内容を確認して
統合してからpushしてください。強制pushは不要です。
同梱のGitHub Actionsはpush/PR時にWindowsとLinuxでテスト・静的チェックを実行します。
Miroの認証情報はCIに不要です。

## 検証範囲と制約

2026-09-21、Windows / Python 3.11.4の新規仮想環境でインストールを確認し、
**pytest 111件成功、Ruffの静的・整形チェック成功、pip check成功**を確認しました。
Pillow 12.3.0、requests 2.34.2、python-dotenv 1.2.3、pytest 9.1.1での結果です。
生成した320×200のJPGから40×25マス（1,000枚）のJSONと640×400のPNGを生成し、
PNGの目視確認も実施しました。

gray除外の追加後は**pytest 141件成功**、Ruffの静的・整形チェックとpip checkも成功しています。
生成したgray混在JPGで1,600マス中800枚、全grayで5,000マス中0枚となることを確認しました。
利用者指定のローカル画像でも、100列・6,700マスから1,526枚分の配置データを生成できました。
これらはAPI送信なしの検証で、PNGの透明度とJSONの作成/除外の対応も確認しています。

ローカルのテスト・モックAPI・生成JPGによるdry-runで検証しています。
加えて、利用者の環境で実Miroボードへの書き出し成功が確認されています。
これは初回版の確認結果です。gray除外後の実ボードでの空白表示は、今回のローカル検証には含めません。
実画面の色・影・寸法の厳密な比較は実施していません。GitHub Actionsの実行結果は
リポジトリのActionsタブで確認してください。

作成のロールバック・自動削除・ボード上の付箋検索・OAuth自動更新・ディザリングは実装していません。
記録後にユーザーが付箋を移動・削除した場合も、再開時はローカル記録を信頼してスキップします。
APIの冪等キーに依存しないため、状態ファイルを失うと安全な自動再開はできません。
状態は一時ファイルのfsyncと原子的置換で保存しますが、電源断・ストレージ故障まで含む
完全なexactly-onceは保証しません。実行記録はローカルディスク上で保管してください。
