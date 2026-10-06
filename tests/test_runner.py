import json
import sys

from noisefloor import runner


def test_parse_output_variants():
    assert runner.parse_output('{"score": 7.5, "label": "accept"}') == (7.5, "accept")
    assert runner.parse_output('{"verdict": "REJECT"}') == (None, "REJECT")
    assert runner.parse_output("some log line\n0.42\n") == (0.42, None)
    assert runner.parse_output("PASS") == (None, "PASS")
    assert runner.parse_output("") == (None, None)
    assert runner.parse_output("two words here") == (None, None)


def test_run_command_logs_every_draw(tmp_path):
    items_dir = tmp_path / "items"
    items_dir.mkdir()
    (items_dir / "a.txt").write_text("alpha")
    (items_dir / "b.txt").write_text("beta")
    # judge: score = length of input file; deterministic → zero noise
    cmd = f"{sys.executable} -c \"import sys; print(len(open(sys.argv[1]).read()))\" {{input}}"
    out = tmp_path / "log.jsonl"
    rows = runner.run_command(cmd, runner.load_items(items_dir), draws=3, out=out, quiet=True)
    assert len(rows) == 6
    logged = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(logged) == 6
    scores = runner.group_scores(logged)
    assert scores["a.txt"] == [5.0, 5.0, 5.0]
    assert scores["b.txt"] == [4.0, 4.0, 4.0]


def test_measure_in_process_with_labels():
    calls = []
    def judge(item, text):
        calls.append(item)
        return "accept" if item == "x" else {"label": "reject", "score": 2}
    rows = runner.measure(judge, {"x": "", "y": ""}, draws=2)
    assert len(rows) == 4 and len(calls) == 4
    labels = runner.group_labels(rows)
    assert labels == {"x": ["accept", "accept"], "y": ["reject", "reject"]}
