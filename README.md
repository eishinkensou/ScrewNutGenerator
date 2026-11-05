# ScrewNutGenerator — ISO ボルト＆ナット生成スクリプト(Autodesk Fusion)

ISO メートル並目ねじ **M2〜M20** のボルトとナットを、実形状のねじ山(Fusion のモデル化ねじ)付きで生成する
Autodesk Fusion 用 Python スクリプトです。3D プリント向けに、印刷向きの配置・ねじクリアランス・張り出し補正を
ダイアログで指定できます。

An Autodesk Fusion script that generates **ISO metric coarse-thread bolts and nuts (M2–M20)** with real modeled
threads, laid out for FDM printing with adjustable thread clearance and overhang compensation.
English notes are at the bottom of this page.

- 印刷済みサンプルと造形プロファイル(Bambu Lab H2C / PETG): MakerWorld
  [GoriSpe (@GorillaSpecial)](https://makerworld.com/ja/@GorillaSpecial) の
  「ISO ボルト＆ナット M3〜M12｜Fusion ねじ生成スクリプト付き」
- MakerWorld には Python ファイルを添付できないため、スクリプトはこのリポジトリで配布しています

## ファイル

| ファイル | 内容 |
|---|---|
| `ScrewNutGenerator.py` | スクリプト本体(寸法表・入力チェック・モデリング) |
| `ScrewNutGenerator.manifest` | Fusion がスクリプトとして認識するための定義 |
| `test_dimensions.py` | Fusion 不要部分(寸法表・入力チェック)の単体テスト。`python test_dimensions.py` |

## インストール(Windows / Mac)

1. 右上の **Code → Download ZIP** でダウンロードして展開する(フォルダ名は `ScrewNutGenerator` に)
2. Fusion を起動し、**ユーティリティ → アドイン → スクリプトとアドイン**(`Shift+S`)を開く
3. 「スクリプト」タブの **+** で、展開したフォルダ(`ScrewNutGenerator.py` と `.manifest` があるフォルダ)を追加する
4. 一覧の **ScrewNutGenerator** を選んで **実行**

毎回「+」で追加したくない場合は、フォルダごと Fusion のスクリプトフォルダにコピーしてください。

```
Windows: %APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\ScrewNutGenerator\
Mac:     ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/ScrewNutGenerator/
```

## ダイアログの項目

| 項目 | 初期値 | 説明 |
|---|---|---|
| 生成対象 | 両方 | ボルト / ナット / 両方 |
| 呼び径(並目) | M8 | M2, M2.5, M3, M4, M5, M6, M8, M10, M12, M14, M16, M20(ピッチは並目固定) |
| 頭の形 | 六角穴付き | 六角(ISO 4017)/ 六角穴付き(ISO 4762)/ ボタン(ISO 7380)/ 皿(ISO 10642) |
| ねじ長さ | 25 mm | 頭を含まない呼び長さ(皿のみ全長) |
| ねじ部長さ | 0 mm | 先端から測ったねじ部の長さ。0 = 全ねじ |
| 内ねじクリアランス | 呼び径ごとの推奨値 | ナット側。呼び径を変えると推奨値に自動で切り替わる |
| 外ねじクリアランス | 0 mm | ボルト側 |
| 張り出し補正(軸方向) | 呼び径ごとの推奨値 | 下向きフランクの垂れ分を余分に逃がす |

- 実行するたびに新しいコンポーネントを作ります(`M8x25_Allen` / `M8x25_Hex` / `M8x25_Button` / `M8x25_CSK`、ナットは `Nut_M8`)
- 生成物は既存形状の +X 側に 5 mm 空けて並ぶので、続けて実行しても重なりません
- 配置は印刷向き(ボルトは頭を下にして Z=0、ナットは平置き Z=0)
- 前回の設定を `last_settings.json`(スクリプトフォルダ内)に記憶します
- 作成後に外形寸法・ねじ規格・クリアランスの適用方式をメッセージで表示します

## クリアランスの既定値(PETG で実測)

入力値は径方向のすき間(片側)です。ひっかかり高さ H1 = 0.541 × ピッチ に対して、H1 以上はエラー、85 % 超で警告になります。

| | M2 | M2.5 | M3 | M4 | M5 | M6 | M8 | M10 | M12 | M14 | M16 | M20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 内ねじクリアランス mm | 0.1 | 0.15 | **0.15** | 0.2 | **0.2** | 0.3 | **0.55** | 0.55 | **0.5** | 0.6 | 0.6 | 0.75 |
| 張り出し補正 mm | 0 | 0 | **0** | 0.05 | **0.05** | 0.15 | **0.3** | 0.3 | **0.3** | 0.35 | 0.35 | 0.4 |

太字は **Bambu PETG Basic / 0.12 mm 層 / 0.4 mm ノズル / テクスチャ PEI、ボルト側 0 mm** の印刷テストで嵌合を確認した値、
それ以外はピッチからの目安です。

- 推奨フィラメントは PETG。PLA / ABS / ナイロンや他の機種では嵌合が変わります。**きつければ内ねじクリアランスを +0.05 mm ずつ、
  ゆるければ −0.05 mm ずつ**再生成して合わせてください(M8 以上は張り出し補正も一緒に)。既定値だけ用意し、細かい調整は使う方にお任せするスタイルです
- ナットはベッド接地面積が小さいのでブリム(外側 5 mm)を推奨。ナット底面には象足逃げの浅い座ぐりが入っているので、象足補正 0.15 mm 程度で問題ありません
- ねじ面にクリアランスを付ける方式は、面のオフセット(OffsetFacesFeatures)を第1候補とし、失敗したときは軸方向シフト交差に自動で切り替えます。どちらを使ったかは作成後のメッセージに出ます

## 寸法の根拠

ISO 4762(六角穴付き)/ ISO 4017(六角)/ ISO 7380(ボタン)/ ISO 10642(皿)/ ISO 4032(ナット)。ねじは ISO 261 並目。

## 動作確認環境

Autodesk Fusion 2706 以降(2025年11月版で追加された OffsetFacesFeatures を使用)、Windows 11。印刷テストは Bambu Lab A1 mini / H2C、PETG Basic。

## ライセンス

MIT License(`LICENSE` 参照)。MakerWorld に掲載しているサンプルモデル(3MF)の方は MakerWorld 側のライセンスに従います。

---

## English

**Install**: Code → Download ZIP, unzip (keep the folder name `ScrewNutGenerator`), open Fusion → Utilities → Add-Ins →
Scripts and Add-Ins (`Shift+S`), press **+** on the Scripts tab, pick the unzipped folder, select **ScrewNutGenerator** and **Run**.
Or copy the folder into Fusion's Scripts folder (`%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\` on Windows).

**Dialog**: target (bolt / nut / both), size M2–M20 (coarse pitch), head style (hex ISO 4017, socket cap ISO 4762, button ISO 7380,
countersunk ISO 10642), length, thread length (0 = fully threaded), internal / external clearance, overhang compensation.
Picking a size switches the clearances to the recommended values. Parts are placed print-ready (bolt head down, nut flat, Z=0)
and 5 mm apart along +X, so repeated runs never overlap. The last settings are remembered in `last_settings.json`.

**Defaults** were measured with Bambu PETG Basic, 0.12 mm layers, 0.4 mm nozzle, textured PEI, bolt clearance 0
(bold values in the table above were print-tested: M3, M5, M8, M12). Other filaments or printers will fit differently:
if too tight add +0.05 mm to the internal clearance, if loose subtract 0.05 mm, and regenerate. Keep a 5 mm outer brim on the nuts.

**Dialog language** is Japanese. Dimensions follow ISO 4762 / 4017 / 7380 / 10642 / 4032 and ISO 261 coarse pitch; threads are
Fusion modeled threads. MIT licensed.
