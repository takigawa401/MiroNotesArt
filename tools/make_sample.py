"""認証不要の動作確認に使う、色グラデーションのJPGを生成する。"""

from pathlib import Path

from PIL import Image


def main():
    path = Path("images/sample.jpg")
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 200))
    image.putdata(
        [
            (round(255 * x / 319), round(255 * y / 199), round(255 * (1 - x / 319)))
            for y in range(200)
            for x in range(320)
        ]
    )
    try:
        with path.open("xb") as output:
            image.save(output, format="JPEG", quality=95)
    except FileExistsError:
        print("images/sample.jpg は既に存在します。上書きせず終了しました。")
        return
    print(f"動作確認用JPGを作成しました: {path.resolve()}")


if __name__ == "__main__":
    main()
