# 0003 EEG の専門家の選定基準で絞り込めるようにする

状態: 実施中(2026-11-20 開始)
関連: [plans/0002](0002-documents-check-survey.md)

maintainer の指示(2026-11-20): EEG の専門家が示した選定基準で絞り込めるように、情報を集め、絞り込みの機能を実装する。
DB は基準の判定(使える・使えない)を書かない。基準に使う値を、出典つきで持ち、ページで条件を選べるようにする。

## 1. 基準と DB の対応

| 基準 | 使う値 | 現状 |
|---|---|---|
| PubMed に載っている | `paper_journals.pmid`(OpenAlex が返す PubMed 番号) | 取得済み。番号が無いことは「PubMed に無い」の証明ではないので、ページは「番号なし(OpenAlex に無い)」と書く |
| Q1 ジャーナル | `journal_rankings`(SCImago の四分位) | 取り込みの道具は完成。SCImago が機械的なアクセスを 403 で拒むため、maintainer が CSV を手で保存する必要がある(`tools/harvest/sjr_import.py` の説明) |
| ジャーナルの分野 | `paper_journals.fields`・`subfields`(OpenAlex のジャーナル分類) | 取得済み。「神経科学・生体医工学」「教育学」は分類の名前で選ぶ |
| 被験者群 | `participant_groups.condition` | 既存。絞り込みあり |
| 被験者数 | `n_subjects_reported` | 既存。範囲の絞り込みあり |
| 1 人あたりの計測時間 | `hours_per_subject_reported`(資料の値)と、合計時間÷被験者数(計算値、別の絞り込み) | 列と絞り込みを追加。値の収集はパイロット中 |
| 計測日数 | `days_per_subject_reported` | 列と絞り込みを追加。基準の「5日以上」の意味(1 人あたり 5 日か)は maintainer に確認 |
| EEG チャネル数 | `n_channels_eeg` | 既存 |
| チャネル配置 | `montage_system` | 既存。10-05・10-10・10-20・ear |
| ライセンス | `license_spdx` | 既存 |
| 申請書類不要 | `access_tier` | 既存 |
| 計測デバイス | `acquisition_setups.device_manufacturer`・`device_model` | 全体調査を `local/device_survey.md` に作成。メーカーの絞り込みは既存 |

## 2. 取得の方法

- ジャーナル: OpenAlex(論文の DOI 50 件ずつ。公開の上限よりずっと少ない 25 リクエスト)。`tools/harvest/journals_*.py`
- 1 人あたりの時間・日数: 資料(README・論文)に書かれた文を、引用つきで審査役が拾う。計算や推測はしない(`cache/audit/DUR_PROMPT.md`)。他の条件(ライセンス・チャネル数)を満たす候補 1,583 件から始める
