# STEP 85 §8: how the built front end handles the null fields (for Claude; panel/src not edited)

Method: the real app on a scratch port with the JSON forced to each null case, built `panel/dist` (index-C66PAvYc.js), real browser, console watched.

## Breaks the page (blank screen, uncaught TypeError)
- `Home.views = null` -> Inicio is blank: `TypeError: Cannot read properties of null (reading 'views')`. The API returns null when `senal.json` is missing.
- `Meta.openrouter.spentUsd = null` -> the whole app is blank: `TypeError: Cannot read properties of null (reading 'toFixed')`. The API returns null when the month's spend cannot be read.
- `Meta.openrouter.perVideoCapUsd = null` -> same blank screen and the same TypeError (the API returns null when `costs.openrouter_per_short_usd` is missing from config).

## Handled without errors (console clean)
`Meta.openrouter.perVideoAvgUsd`, `Meta.statsReadAt`, `NextVideo` null, `NextVideo.emoji`/`family`/`slot`/`thumb`/`xp`, empty `tags`/`words`, all four `facts` null (render shows «sin dato»), `Slot.emoji`/`views`, `ViewsBlock.prevViews`, empty `formats`, `Sequel.emoji`,
`ScheduleInfo.next`, `ReviewItem.frame0.src`, empty `strip`, `durationS`, `costUsd`, `design`, `items`, and every `Check.ok`/`detail` null.
(Not forced: `Job.*` nulls, `Game` with all achievements locked, `Home.next.thumb` with a real placeholder.)

## Other
- On Inicio the theme dropdown opens underneath the «Agenda de hoy» card: a real pointer click on «Siempre noche» is intercepted by `h3#ag-t` (z-index/stacking). Keyboard or a programmatic click works.
- The theme menu exists only on Inicio, not on Revisar.
