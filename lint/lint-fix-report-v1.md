=== LINT FIX SUMMARY — calendario-scolastico (fix v1) ===
Generated: 2026-06-22
Source report: calendario-scolastico\lint\lint-report-v1.json

AUTO-FIXED (29 issues):
  Applied via `ruff check --fix --unsafe-fixes`:
  - SIM103 (6): Return condition directly — calendario_generator.py (×2), ordinary_placement.py, post_ordinary_optimizer.py (×2), provaO.py
  - SIM108 (3): Ternary operator — post_ordinary_optimizer.py (×2), post_ordinary_optimizer.py:16 (fixed inline)
  - SIM105 (2): contextlib.suppress — app\__init__.py, app\utils\__init__.py
  - E712 (1):   Avoid equality comparison to False — routes\classi.py:178
  - PLR1714 (1): Merge comparisons — post_ordinary_optimizer.py:151
  - I001 (11):  Import block un-sorted (side-effect of contextlib import) — app\__init__.py, routes\anni.py, routes\classi.py, routes\docenti.py, routes\festivita.py, routes\materie.py, routes\orario.py, routes\stage.py, routes\vincoli.py, utils\__init__.py, utils\post_ordinary_optimizer.py
  (no action needed)

SUB-AGENT FIXED (5 issues):
  SIM102 (5): Merged nested `if` into single `if … and …` in:
    - app\utils\ordinary_placement030326.py:139
    - app\utils\post_ordinary_optimizer.py:284
    - app\utils\utils_scheduler.py:157
    - app\utils\utils_scheduler.py:231
    - app\utils\validator.py:291

UNRESOLVED BY SUB-AGENTS (0 issues — needs human):
  (none)

NEW ISSUES INTRODUCED (1):
  - app\utils\post_ordinary_optimizer.py:278 — E501 — Line too long (99 chars).
    Introduced by SIM102 merge. The project ruff config enforces 88-char lines;
    the merged condition slightly exceeded it. ⚠ Review before committing.

HUMAN-REQUIRED (311 issues — not attempted):
  VUL-unused-function (64):
    Flask route handlers flagged as unused by Vulture. These are registered via
    @app.route decorators and are NOT dead code. Safe to ignore unless you are
    actively removing routes.
  C901 (24): Cognitive complexity too high — functions need manual refactoring
  PLC0415 (26): imports inside function bodies — intentional pattern in several utils
  PLR2004 (22): Magic numbers — need named constants
  PERF102 (22): dict.items() used when only .values() needed
  B023 (15): Lambda/closure captures loop variable by reference (real bug risk)
  E701 (14): Multiple statements on one line (colon)
  PLR0912 (14): Too many branches
  VUL-unused-variable (11): Vulture dead-variable findings (60% confidence — review manually)
  PLR0915 (10): Too many statements
  N806 (9): Variable names should be lowercase
  RUF003 (9): Ambiguous quote characters in comments
  PTH118 (8): os.path.join() → pathlib
  RUF059 (8): Unpacked variable never used
  E402 (7): Module-level import not at top of file
  PERF401 (6): list.append in loop → list.extend
  SIM110 (5): for loop → any()/all()
  PLW0603 (4): global statement discouraged
  PTH103 (4): os.makedirs() → Path.mkdir()
  E741 (4): Ambiguous variable name (l, L)
  F821 (4): Undefined name (real bug risk — review immediately)
  RUF002 (4): Ambiguous quote in docstrings
  S105 (3): Possible hardcoded password (SECRET_KEY)
  FURB171 (3): Membership test against single-item container
  VUL-unused-class (3): Unused classes (60% confidence)
  SIM118 (2): key in dict.keys() → key in dict
  PTH208 (2): os.listdir() → Path.iterdir()
  VUL-unused-attribute (1): Unused attribute
  PLW2901 (1): Loop variable overwritten
  N999 (1): Invalid module name (provaO.py)
  PLR0911 (1): Too many return statements

  ⚠ Priority items for manual review:
    - F821 (4 occurrences): Undefined names — likely real runtime bugs
      app\utils\diagnostica.py:87 — giorno_label_prev
      app\utils\ordinary_pulp.py:54 — slot_e_fisso
      app\utils\ordinary_pulp.py:62 — giornata_bloccata
      app\utils\ordinary_pulp.py:296 — docente_disponibile_global
    - B023 (15 occurrences): Closures capturing loop variables by reference
      in provaO.py — real concurrency/correctness risk if lambdas are called later
    - S105 (3): Hardcoded SECRET_KEY — use environment variable in production

FULL REPORTS:
  Fix log  → calendario-scolastico\lint\lint-fix-report-v1.md   (this file)
  HTML     → calendario-scolastico\lint\lint-report-v3.html
  JSON     → calendario-scolastico\lint\lint-report-v3.json
  (v2 was an intermediate re-lint before I001/SIM108 cleanup pass)
