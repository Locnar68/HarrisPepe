# 02 — Folder Structure (for whoever owns the data)

> The folder path **is** the logic. If you put a file in the wrong folder,
> the AI will answer the wrong question about it. Follow these rules.

## Rules

1. **Every file lives under `Properties/<property>/<category>/`.** Anything outside that tree is ignored.
2. **Property folders are hyphenated, no spaces.** `15-Northridge`, not `15 Northridge`.
3. **Category folders use the exact `NN-Name` prefixes.** See table below.
4. **Sub-folders inside a category are OK.** `04-Permits/2025-expired/x.pdf` works.
5. **Don't put files directly at the property root.** They'll be ignored.

## Category folders

| Folder           | Contents                               | Tag (`doc_type`) |
|------------------|----------------------------------------|------------------|
| `01-Acquisition` | Closing docs, title, deed, purchase    | `legal`          |
| `02-Financials`  | P&Ls, bank statements, tax returns     | `finance`        |
| `04-Permits`     | Building permits, inspections, codes   | `permit`         |
| `06-Invoices`    | Contractor bills, checks, receipts     | `billing`        |
| `07-Photos`      | Progress photos, site conditions       | `image`          |

Adding a new category? Edit `config/config.yaml → metadata.category_folders`.

## Canonical tree

```
<root connector folder>/          ← this is the folder ID in config.yaml (Drive)
├── 15-Northridge/
│   ├── 01-Acquisition/
│   │   ├── closing-statement.pdf
│   │   └── title-insurance.pdf
│   ├── 02-Financials/
│   │   ├── 2024-P&L.xlsx
│   │   └── bank-stmt-2025-09.pdf
│   ├── 04-Permits/
│   │   ├── permit_A1.pdf
│   │   └── inspection-2025-08-12.pdf
│   ├── 06-Invoices/
│   │   ├── plumber-check-2025-07.jpg       ← handwritten; Gemini reads it
│   │   └── roofer-invoice-2025-08.pdf
│   └── 07-Photos/
│       ├── pre-demo-front-elevation.jpg
│       └── framing-complete-2025-09.jpg
│
├── 22-Willow/
│   └── ...
│
└── 47-Parkside/
    └── ...
```

## Adding a new property

1. Make a folder: `<NN>-<name>`, two-digit number, hyphenated.
2. Create whichever category folders you'll actually use.
3. Run:
   ```
   python scripts\index.py --discover
   ```
   It prints any new properties. Add them to `config.yaml → metadata.properties` so they show up in `--property=` filter auto-complete.

## What NOT to do

- **Don't rename properties.** Renames create orphaned documents in the index. If you must rename, do it AND run `python scripts/index.py --full`.
- **Don't use emoji or accents in folder names.** Stick to ASCII + hyphens.
- **Don't nest properties inside properties.**
- **Don't put HEIC images in `07-Photos/`.** Convert to JPG first — HEIC isn't on the allowlist.

## Supported file types

`.pdf .doc .docx .ppt .pptx .xls .xlsx .txt .md .html .csv .json .jpg .jpeg .png .gif .bmp .tiff .webp`

Everything else is skipped silently. Google Docs/Sheets/Slides are auto-exported to PDF on sync.
