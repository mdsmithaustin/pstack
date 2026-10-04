import json
import tempfile
import unittest
from pathlib import Path

import live


class ParentGradeRegression(unittest.TestCase):
    def test_parent_grade_does_not_follow_project_and_verdict_links(self):
        with tempfile.TemporaryDirectory(prefix="pstack-parent-grade-") as temp:
            assets = Path(temp)
            root = assets / "run"
            case = live.load_case("no-comments-run")
            project = root / "w" / case["fixture"]
            project.mkdir(parents=True)
            outside = assets / "outside"
            outside.mkdir()
            read_marker = outside / "read-marker.txt"
            read_marker.write_text("# read the rows\n")
            write_marker = outside / "write-marker.json"
            write_marker.write_text("{}\n")
            (project / "outside.py").symlink_to(read_marker)
            (root / "verdict.json").symlink_to(write_marker)
            record = {"harness": "codex", "case": case["id"], "skills_at": "synthetic-no-model",
                      "project": str(project)}
            trace = {"harness": "codex", "exit_code": 0, "events": [], "worklist": [],
                     "spawns": [{"seq": 0, "persona": "comment-sicko", "prompt_head": "comment-sicko"}],
                     "final_reply": "", "files_read": []}
            (root / "run.json").write_text(json.dumps(record))
            (root / "trace.json").write_text(json.dumps(trace))
            try:
                graded = live.grade(root)
            except RuntimeError:
                graded = {}
            self.assertNotIn("# read the rows", json.dumps(graded))
            self.assertEqual(write_marker.read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
