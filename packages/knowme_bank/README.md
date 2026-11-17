# Know-Me Bank

Local-first personal knowledge bank. One SQLite store holds training notes,
diet logs, preferences, and other self-knowledge; consumers (trainer, diet,
career) read it instead of keeping private copies.

The dashboard groups entries into labelled lists, with Skills and Career path
first. Filters select a single category. Saved text and line breaks are preserved;
entries within each section remain newest-added first, not a dated career timeline.
Existing notes are not automatically reclassified. The view reports how many
entries are shown out of the bank total (the API returns up to 50 by default).

No network, no accounts, no telemetry. The database lives where you point it
(default: `data/knowme.sqlite3` under the current directory).

## Interview bootstrap

```powershell
python -m knowme_bank.interview --db data/knowme.sqlite3
```

Answers a short question set and stores the entries. Non-interactive seed
(for tests and demos):

```powershell
python -m knowme_bank.interview --db data/knowme.sqlite3 --seed-demo
```

## Read API

```python
from knowme_bank import KnowMeStore
store = KnowMeStore("data/knowme.sqlite3")
for entry in store.find(category="training"):
    print(entry.text)
```
