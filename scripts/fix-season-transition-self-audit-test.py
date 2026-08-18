from pathlib import Path

path = Path("companion/source/app/tests/test_season_transition.py")
text = path.read_text(encoding="utf-8")
old_import = "from datetime import date\n"
new_import = "from dataclasses import replace\nfrom datetime import date\n"
if text.count(old_import) != 1:
    raise SystemExit("date import marker changed")
text = text.replace(old_import, new_import, 1)
old = "    applicant = _applicant()\n    applicant.rio_score = 375\n"
new = "    applicant = replace(_applicant(), rio_score=375)\n"
if text.count(old) != 1:
    raise SystemExit("immutable applicant test marker changed")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
