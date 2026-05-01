# pid-zoektool

CLI to search a P&ID (Piping & Instrumentation Diagram) PDF by tag or free text.
Built around `UNIT 53.pdf` but works on any P&ID with similar tag conventions.

## Requirements

- Python 3.8+
- `poppler-utils` (`pdftotext`, `pdfinfo`)

```
sudo apt-get install poppler-utils
```

## Usage

```
python3 pid_zoektool.py [--pdf "UNIT 53.pdf"] <command>
```

The first command builds a per-page text cache in `.pid_cache/`. Use `--refresh`
to rebuild after replacing the PDF.

### Commands

- `tags` — count of unique tags per category
- `list <category>` — list all tags in `equipment` / `valve` / `instrument` /
  `line` / `pid_ref`. Pass `--with-pages` to show where each appears.
- `search <query>` — tag-style search across all categories. Flags:
  - `-t/--text` full-text search instead of tag search
  - `-c/--category <cat>` restrict to a category (repeatable)
  - `-p/--page <n>` restrict to one page
  - `--case` case-sensitive
  - `--limit <n>` cap result count (default 200)
- `info <tag>` — pages, hit count and per-occurrence snippets for one tag.
  Substring lookup is supported when unambiguous.
- `page <n>` — dump the raw text of page `n`.

### Examples

```
python3 pid_zoektool.py tags
python3 pid_zoektool.py list equipment --with-pages
python3 pid_zoektool.py search 53MV-0005
python3 pid_zoektool.py search 53EA -c equipment
python3 pid_zoektool.py search deaerator -t --limit 5
python3 pid_zoektool.py info 53EA-03
python3 pid_zoektool.py page 1
```

## Categories

Tags are categorized by prefix:

- **valve** — `MV`, `SV`, `NRV`, `CV`, `GV`, `BV`, `XV`, `PV`, `TV`, `LV`, `FV`
- **instrument** — common ISA letter codes: `AI/AT`, `FI/FT/FE/FC`, `LI/LT/LC/LG`,
  `PI/PT/PC/PG`, `TI/TT/TC/TE/TG`, alarms `xAH/xAL/xSH/xSL`, etc.
- **equipment** — anything else matching `53XX-NN[suffix]` (e.g. `53BG-01`,
  `53EA-03`, `53FA-10S`)
- **line** — full line numbers like `4"ES53003-6-1B2NB-NT-H`
- **pid_ref** — drawing references like `082755C-053-PID-0021-0001-03`
