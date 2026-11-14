# 0002 資料調査(documents check)を一通り終わらせる

状態: 実施中(2026-11-14 開始)
関連: [discussions/0002](../discussions/0002-align-with-ser-principles.md)(進め方の決定)、[plans/0001](0001-initial-plan.md)

maintainer の指示(2026-11-14):「実装調査はまだやらず、資料調査の段階を一通り終わらせる」。
実装調査(レシピを作り readme の `## The data` を書く)は、この計画が済んでから。

## 1. 情報源ごとの進め方と状況

| 情報源 | 候補の数 | 進め方 | 状況(2026-11-14) |
|---|---|---|---|
| OpenNeuro | 612(EEG・iEEG・MEG で検索)。EEG か iEEG を含むものだけ登録 | API とメタデータ文書から機械的に(`tools/harvest/openneuro_*`) | 544 件登録(67 件は EEG・iEEG なし、1 件は削除済み)。同名の 9 組は `possibly_same_as` |
| PhysioNet | 38(題名・要旨に EEG・睡眠など) | ページを読んで EEG を配布しているか判断し、API とページから(`physionet_register.py`) | 30 件登録、8 件対象外 |
| BNCI Horizon 2020 | 32 | 一覧ページから(`bnci_register.py`) | 31 件登録、1 件対象外(fNIRS のみ) |
| TUH EEG | 7 | 配布ページを読む | 登録済み。ライセンスは申請書(PDF)を未読 |
| SEED シリーズ | 13 | 各説明ページとライセンス PDF を読む | 12 件登録。SEED-DV は未登録 |
| Excel の残り | DEAP | 配布ページ | **証明書エラーで開けない**(maintainer のブラウザで確認が要る) |
| その他の個別 | DREAMER、OpenBMI、BCI Competition 2020 | ページを読む | 登録済み |
| MOABB のカタログ | 約 200 行(7 つの CSV) | カタログは二次資料。各データセットの元の配布先(Zenodo・figshare・個人サイトなど)を開いて登録 | Zenodo の 27 件を登録(`zenodo_register.py`)。再アップロードと名乗る 4 件は保留。Zenodo 以外は未着手 |
| Zenodo | 「EEG」などで検索した dataset 型の記録(約 1,500〜2,000) | 一覧を取得し、EEG の記録を配布するものを選ぶ。派生物・結果・コードだけの記録は対象外 | 検索結果の全記録を保存し、EEG の記録を述べるもの 809 件を登録(`zenodo_search.py`・`zenodo_register.py`)。残りは名前・説明に EEG の記録が書かれていない等で未登録(理由は `cache/zenodo_skipped.tsv`)。検索語のうち brain-computer interface 以降は途中で止めた |
| Hugging Face | 「eeg」で 1,000 件以上 | 再アップロードが多い。元のデータセットが分かるものは経路(mirror)と別名にする | EEGDash の 738 件は OpenNeuro・NEMAR へのポインタなので対象外。残りのうちカードが EEG の記録を述べる 7 件を登録(`hf_register.py`) |
| figshare・OSF・Kaggle・Harvard Dataverse・Mendeley Data | 未計数 | figshare は検索で 4,096 件、題名で絞って 121 件を登録(`repo_register.py`)。NEMAR(nm…)は 314 件を登録(`nemar_register.py`)。OSF・Kaggle・Dryad・Mendeley・Harvard Dataverse の検索は未着手 |
| foundation model 論文の学習・評価データ | CBraMod・REVE・SingLEM で 158 件(重複を除く) | 論文の表と参考文献から配布先を開いて登録(`repo_register.py` と手作業)。どの論文が何を使ったかは `local/paper_usage/` | 157 件が DB にある。EPFLP300 は配布ページが開けず未登録。6 件は入手経路が未確認 |

## 2. 量と順番

Zenodo と Hugging Face の候補が多く(合わせて 2,500 件以上)、1 件ずつページを読む作業になる。
計画 0001 §4 の方針(入手経路を重視し、自動で取れて学習に使えるものから)に従い、次の順で進める。

1. 機械で読める大きなリポジトリ(OpenNeuro・PhysioNet・BNCI)── 済み/実施中
2. よく使われるもの: MOABB のカタログと foundation model 論文に出てくるもの(元の配布先が自動取得できるものを先に)
3. Zenodo の候補(API でライセンスと公開状態が読める。公開・ライセンスつきから)
4. Hugging Face・Kaggle・その他

## 3. 残っていること(このセッションで終わらないもの)

- 上の表の「未着手」すべて
- OpenNeuro のデータセットのうち、他の配布先のデータを BIDS に変換したもの(例: PhysioNet のデータの変換)の関係づけ(`relations`)
- 論文の本文を読まないと分からない値(パラダイムの分類・被験者群の要約値・品質情報・課題の手順)。OpenNeuro はメタデータ文書だけを読んでいる
- Claude の環境から開けない資料: DEAP の配布ページ(証明書エラー)、GigaDB の利用規約ページ(描画されない)
