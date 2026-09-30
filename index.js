/**
 * Entry artifact for the market's install/update validator.
 *
 * This package is a DSH **bundle**: the loader never imports this file. Its
 * `cordis.patch.yml` is what actually composes the `scrape` preset, and the
 * only module the loader imports from here is the subpath
 * `@emo-bird/dsh-preset-scrape/lean-agent.js` (see that row in the patch).
 *
 * Why this file exists at all: `dshmarket` gates install and update on
 * `hasLoadableEntry()`, which reads `main` / `exports` / a bare `index.js`
 * fallback (`dshmarket/lib/profile.js` `entryArtifactExists`). A patch-only
 * bundle with none of those is judged "arrived without the entry file its
 * package.json points at" and the update is rolled back — even though the
 * bundle works, because the patch is the entry point and not a JS module.
 *
 * So this file is a deliberate no-op marker, not dead code: deleting it
 * re-breaks every marketplace update of this bundle. It exports nothing and
 * must stay importable (syntax-valid ESM) in case a future loader change
 * decides to import the root specifier.
 */

export const name = 'dsh-preset-scrape';
