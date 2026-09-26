<!-- TALOS FILE VERSION: v1.2.0 -->
# TALOS Greek mythology demo dataset

`data/sample/talos_demo.csv` is a synthetic teaching table. It contains curated,
short summaries of selected figures and traditions; it is not a historical
source, complete catalogue, or claim that every detail had one canonical
version. Parentage and role notes are intentionally source-aware. A blank
parent field means the selected summary leaves that field open or the source
traditions differ; it is not a claim that the deity had no parents.

## Source basis

- Hesiod, *Theogony*, translated by Hugh G. Evelyn-White (Loeb Classical Library,
  1914): [Theoi transcription](https://www.theoi.com/Text/HesiodTheogony.html).
  Used for the primordial sequence, Titan genealogy, Olympian parentage, and
  selected divine lineages.
- *Homeric Hymn to Demeter*, translated by Gregory Nagy:
  [University of Houston transcription](https://www.uh.edu/~cldue/texts/demeter.html).
  Used for the Demeter–Persephone mythic arc. The note field identifies cases
  where accounts differ or the row is a modern grouping.
- *Homeric Hymn to Hermes*, translated by Hugh G. Evelyn-White:
  [Theoi transcription](https://www.theoi.com/Text/HomericHymns3.html).
  Used as an additional reference for Hermes' birth narrative.
- *Homeric Hymn to Pan*, translated by Hugh G. Evelyn-White:
  [Theoi transcription](https://www.theoi.com/Text/HomericHymns3.html).
  Parentage varies among traditions; the dataset note identifies the selected
  hymn account.

The dataset includes deliberate quality signals: category casing and spacing
variants, several blank parent fields, one exact duplicate row, one all-empty
column, and one constant teaching label. `teaching_measure_demo_only` is an
invented numeric field with an outlying value for practicing the IQR workflow.
It is not a mythological fact, ranking, or measure of divine power.
