# External disaster evidence assessment

Assessment date: 2026-10-20. This work supports issue #31 and future flood-label curation.
It does not change the formal split, approve candidate reviews or add confirmed flood labels.

## TWDisaster

[TWDisaster](https://github.com/KageRyo/TWDisaster) revision
`067b54ef1f9855f37ca766c4e205fcf284557db0` contains 76 historical events and 395 response
observations covering 2001–2025. Its tracked checksum inventory passed local verification.
Three observation rows mention Minxiong in their reported area; 13 mention Chiayi. These are
source-coverage counts, not a count of confirmed inundation events. None overlaps the five formal
radar windows in July 2026.

| Observation / event | Source and finding | What still needs review |
| --- | --- | --- |
| `TWD-O00016` / `TWD-E0004`, 2001 Toraji | WRA original PDF retrieved and checksum-matched; printed page 32 describes reported levee seepage and an inspection, while page 17 includes Minxiong in a broader inundation summary | Geographic consistency and event start/end; the cited inspection row alone does not establish an inundation footprint |
| `TWD-O00163` / `TWD-E0037`, 2013 Kong-rey | [Highway authority notice](https://www.thb.gov.tw/News_Content_table.aspx?n=87&s=43690), section one, item one, explicitly attributes the Dalin–Minxiong road closure to flooding | The road spans two townships; the notice's 20:00 status heading does not establish the dataset's midnight observation timestamp or a flood onset/end |
| `TWD-O00276` / `TWD-E0056`, 2018 August heavy rain | [Highway authority report four](https://www.thb.gov.tw/News_Content_table.aspx?n=87&s=57769), section one, item one, explicitly describes inundated lanes on Highway 1 at 258.2–258.5 km; report status is 17:00, publication is 17:19 | The enclosing section calls closures precautionary, but the individual item describes actual lane flooding; retain both facts and establish spatial extent and start/end independently |

The last two original notices were read through the web research tool. Direct local downloads
returned a 212-byte JavaScript challenge with HTTP 200, not the notice body. Those response hashes
must not be represented as hashes of the original notices. TWDisaster itself has no verified
snapshot hash for these two source rows. A future immutable source capture still needs content
validation and a recorded acquisition time.

The WRA original PDF was retrieved separately and its bytes match TWDisaster's published snapshot
SHA-256, `e358db9ccc537e11d7260c71d9b2e5709e008036d01a27247c76a2bf75faed37`.
Printed page 32 was also rendered and inspected visually. Its Minxiong rows describe levee
seepage, gate management and high water, and neighboring geographic descriptions are inconsistent
with their township cells. Preserve those source discrepancies for review instead of silently
geocoding the rows. The broader page 17 narrative supports historical flooding context, but does
not establish a precise Minxiong event window or polygon. The original remains external; its
source URL and rights reference are in TWDisaster source record `TWD-S0003`.

These two notices are useful positive-evidence candidates, not two training-ready labels.
They cannot satisfy the project's 10 positive / 20 negative reviewed-event gate. Absence from a
non-exhaustive historical catalogue is unknown, never an observed non-flood event. Do not invent
event end times, precise coordinates, reviewer identities or weather classifications.

TWDisaster's selection, arrangement, prose and schemas use CC BY 4.0; upstream source rights remain
separate. Attribute TWDisaster and the original authority when using a row. See its
[data licence](https://github.com/KageRyo/TWDisaster/blob/067b54ef1f9855f37ca766c4e205fcf284557db0/DATA_LICENSE.md)
and the corresponding source row's rights declaration. No original report or bulk historical
observations are redistributed here.

## CWA context acquisition

The official [monthly statistics page](https://www.cwa.gov.tw/V8/C/C/Statistics/monthlydata.html)
exposes a dated
[July 2026 table](https://www.cwa.gov.tw/V8/C/C/Statistics/MonthlyData/MOD/2026_7.html).
It was retrieved over verified TLS and preserved externally with its SHA-256. Monthly station
statistics cannot establish the weather mechanism or event-time QPE/gauge agreement for a
six-to-ten-hour radar window. The current weather-PDF page likewise does not establish historical
coverage. Formal-event context and event-time validation therefore remain pending.

## Next evidence work

1. Obtain content-validated immutable copies of the two highway notices and resolve the WRA
   report's spatial inconsistencies against independent official evidence.
2. Establish event-time and spatial coverage before producing a flood-label review proposal.
3. Retrieve official context and event-time QPE/gauge observations for each 2026 formal event;
   historical disasters do not substitute for these missing inputs.
4. Keep human decisions separate from machine collection and propose formal split changes only
   with complete evidence. No public forecast or notification gate changes follow from this work.
