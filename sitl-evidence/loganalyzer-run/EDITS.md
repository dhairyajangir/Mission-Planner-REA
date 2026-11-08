Edits made to a scratch copy of `mission-planner-1.3.83-source/LogAnalyzer/py2exe` (the repository copy is unchanged):

- `LogAnalyzer.py`: `except Exception, e:` -> `except Exception as e:`
- `DataflashLog.py`, `tests/TestParams.py`, `tests/TestPitchRollCoupling.py`: `.iteritems()` -> `.items()`
- `imp.py` added: `research-tools/imp_shim.py` (Python 3.12 has no `imp` module)
- Input: the binary log written by the Copter SITL flight in `sitl-evidence/copter-air-modes/`, converted to text by
  `research-tools/bin_to_text_log.py` (the tool reads text logs only); run with `-s` (skip malformed lines; 11 were skipped).
