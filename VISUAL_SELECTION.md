# Visual candidate review and selection

The realistic renderer can collect several independently licensed image candidates for each scene. No paid image API is used.

## Prepare candidates

From the repository root:

```powershell
python cinema.py myscript.txt output.mp4 --style realistic --plan plan.json --content-style history --prepare-assets-only --candidates-per-scene 3
```

Use `--candidates-per-scene 1` through `8` to change the candidate count. The default is 3.

The persistent library is created under:

```text
assets/<script-name>_<script-hash>/
  asset_manifest.json
  contact_sheet.jpg
  asset_selections.example.json
  candidates/
    scene_001/
      c01.jpg
      c02.jpg
      c03.jpg
    scene_002/
      c01.jpg
      ...
```

The contact sheet labels each thumbnail with its scene number and candidate ID. The current automatic/manual selection is marked `[SELECTED]`.

## Choose the image for a scene

1. Open `contact_sheet.jpg`.
2. Find the best candidate for each scene.
3. Copy `asset_selections.example.json` to `asset_selections.json` in the same library folder.
4. Edit only the scene values you want to change. For example:

```json
{
  "1": "c02",
  "2": "c01",
  "3": "c03"
}
```

Scene keys are 1-based scene numbers. Candidate IDs are shown on the contact sheet. Omit a scene key to keep its current selection.

Each candidate's original provider, title, creator, licence, licence URL and source/landing page are retained in `asset_manifest.json`. The selected candidate's provenance is also used in the rendered video's credits.

## Render offline

After reviewing and editing the selection file:

```powershell
python cinema.py myscript.txt output.mp4 --style realistic --plan plan.json --content-style history --offline
```

Offline mode does not contact Wikimedia Commons or Openverse. It renders using the selected local candidate for each scene.

## Resume after rate limits or network failures

Run the same preparation command again. Completed candidate files and their manifest records are retained. The engine attempts to fill any incomplete candidate sets without replacing the existing candidates. If a source is unavailable, already saved candidates remain usable.

## Licence and copyright notes

The downloader conservatively accepts Public Domain, CC0 and CC BY assets. The manifest records source and licence metadata so attribution can be prepared. This is not a legal guarantee: verify the original source page and licence conditions before publishing, especially attribution requirements and any restrictions on the depicted subject or underlying work. User-supplied local images are marked as requiring the user's ownership/licence confirmation.
