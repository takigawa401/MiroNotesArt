"""コマンドラインの入力・出力を調停する。"""

import argparse
import os
import re
import sys
from dataclasses import fields
from pathlib import Path

from dotenv import dotenv_values

from .api import APIError, MiroClient, UnknownResult
from .artifacts import create_run_dir, print_summary, save_artifacts
from .config import Settings
from .imaging import load_mosaic
from .layout import build_notes
from .locking import run_lock
from .runner import upload
from .state import StateError, StateStore, make_plan


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f"引数が不正です: {message}（--help で使い方を確認できます）。")


def parser() -> argparse.ArgumentParser:
    result = Parser(
        description="JPG画像をMiroの16色の付箋アートに変換します。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    result.add_argument("--image", type=Path, required=True, help="入力JPG/JPEG画像")
    result.add_argument("--board-id", help="対象ボードID（MIRO_BOARD_IDより優先）")
    result.add_argument("--columns", type=int, default=40, help="横方向のマス数")
    result.add_argument("--note-size", type=float, default=200, help="付箋の幅")
    result.add_argument("--gap", type=float, default=0, help="付箋間の間隔")
    result.add_argument("--origin-x", type=float, default=0, help="左上の付箋の中心X座標")
    result.add_argument("--origin-y", type=float, default=0, help="左上の付箋の中心Y座標")
    result.add_argument("--max-notes", type=int, default=2500, help="作成枚数の上限")
    result.add_argument("--dry-run", action="store_true", help="PNG/JSONだけ生成しAPIへ送信しない")
    result.add_argument(
        "--output-dir", type=Path, default=Path("output"), help="実行別フォルダーの保存先"
    )
    result.add_argument("--interval", type=float, default=0.1, help="各HTTP送信後の最小待機秒数")
    result.add_argument(
        "--max-retries", type=int, default=5, help="429の再試行回数（初回は含まない）"
    )
    result.add_argument("--timeout", type=float, default=30, help="応答読み取りのタイムアウト秒数")
    result.add_argument("--resume", type=Path, help="再開するstate.json（元の設定も指定）")
    resolution = result.add_mutually_exclusive_group()
    resolution.add_argument(
        "--resolve-created",
        metavar="ROW,COL=ITEM_ID",
        help="確認済みの結果不明付箋を作成済みに記録（API送信なし）",
    )
    resolution.add_argument(
        "--resolve-absent",
        metavar="ROW,COL",
        help="ボード上に存在しないと確認した付箋を未作成に戻す（API送信なし）",
    )
    return result


def credentials(board_argument: str | None) -> tuple[str | None, str]:
    # カレントディレクトリだけを明示的に読む。環境変数を変更しない。
    local = dotenv_values(Path.cwd() / ".env", interpolate=False)
    token = os.environ.get("MIRO_ACCESS_TOKEN", local.get("MIRO_ACCESS_TOKEN") or "")
    board = (
        board_argument
        if board_argument is not None
        else os.environ.get("MIRO_BOARD_ID", local.get("MIRO_BOARD_ID") or "")
    )
    return board.strip() or None, token.strip()


def parse_resolution(value: str, *, created: bool) -> tuple[int, int, str | None]:
    pattern = r"(\d+),(\d+)=([^=\s]+)" if created else r"(\d+),(\d+)"
    match = re.fullmatch(pattern, value)
    if not match:
        raise ValueError("確認結果の指定は 行,列=付箋ID または 行,列 の形式が必要です（0始まり）。")
    return int(match[1]), int(match[2]), match[3] if created else None


def send_or_resolve(args, plan: dict, directory: Path, token: str, settings: Settings) -> None:
    with run_lock(directory):
        store = StateStore.load(args.resume, plan) if args.resume else None
        if args.resolve_created or args.resolve_absent:
            value = args.resolve_created or args.resolve_absent
            store.resolve(*parse_resolution(value, created=args.resolve_created is not None))
            print(
                "確認結果を記録しました。API送信はありません。確認用オプションを外して再開してください。"
            )
            return
        if not plan["notes"]:
            print("作成対象は0枚です。プレビューと配置JSONを保存し、API送信なしで終了しました。")
            return
        if not plan["board_id"] or not token:
            raise ValueError(
                "送信には MIRO_ACCESS_TOKEN と --board-id または MIRO_BOARD_ID が必要です。"
            )
        if any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError(
                "MIRO_ACCESS_TOKEN に空白・制御文字・非ASCII文字があります。値を確認してください。"
            )
        if store is None:
            store = StateStore.create(directory / "state.json", plan)
        print(f"再開用の記録: {store.path.resolve()}", flush=True)
        client = MiroClient(
            token,
            interval=settings.interval,
            max_retries=settings.max_retries,
            timeout=settings.timeout,
            report=lambda message: print(message, flush=True),
        )
        try:
            upload(store, client, report=lambda message: print(message, flush=True))
        finally:
            client.close()
        print("すべての付箋を作成しました。")


def main(argv=None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.resume and args.dry_run:
            raise ValueError("--resume と --dry-run は同時に指定できません。")
        if (args.resolve_created or args.resolve_absent) and not args.resume:
            raise ValueError("確認結果を記録するには --resume が必要です。")
        settings = Settings(**{field.name: getattr(args, field.name) for field in fields(Settings)})
        settings.validate()
        board, token = credentials(args.board_id)
        if board and any(c.isspace() or c in "/?#" for c in board):
            raise ValueError("--board-id にはURLではなくボードID部分だけを指定してください。")
        mosaic, image = load_mosaic(args.image, settings)
        notes = build_notes(mosaic, settings)
        plan = make_plan(image, settings, board, notes, *mosaic.size)
        print_summary(plan)
        if args.resume:
            directory = args.resume.resolve().parent
        else:
            directory = create_run_dir(args.output_dir)
            save_artifacts(directory, plan)
        print(f"出力先: {directory.resolve()}", flush=True)
        if args.dry_run:
            print("確認モード完了: preview.png / layout.json を保存しました。API送信はありません。")
            return 0
        send_or_resolve(args, plan, directory, token, settings)
        return 0
    except UnknownResult as error:
        print(
            f"結果不明: {error} 自動再送しません。"
            "state.json とREADMEの確認手順を参照してください。",
            file=sys.stderr,
        )
        return 3
    except (ValueError, StateError, APIError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "エラー: ファイルを読み書きできません。パス・空き容量・権限を確認してください。",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            "中断しました。state.jsonを指定して再開してください。結果不明があれば先にボードを確認してください。",
            file=sys.stderr,
        )
        return 130
