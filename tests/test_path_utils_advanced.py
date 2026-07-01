"""Advanced tests for path_utils — prefix stripping, session nesting, edge cases."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestResolvePath:
    def test_empty_filename_raises(self):
        from app.utils.path_utils import resolve_path
        with pytest.raises(ValueError):
            resolve_path("")

    def test_whitespace_only_raises(self):
        from app.utils.path_utils import resolve_path
        with pytest.raises(ValueError):
            resolve_path("   ")

    def test_workspace_prefix_stripped(self):
        from app.utils.path_utils import resolve_path
        session = str(Path.cwd())  # neutral path
        result = resolve_path("/workspace/test.md", session)
        assert "/workspace" not in result and "workspace" not in result.split("\\")

    def test_mnt_data_prefix_stripped(self):
        from app.utils.path_utils import resolve_path
        session = str(Path.cwd())
        result = resolve_path("/mnt/data/file.md", session)
        assert "mnt" not in result

    def test_home_user_prefix_stripped(self):
        from app.utils.path_utils import resolve_path
        session = str(Path.cwd())
        result = resolve_path("/home/user/doc.md", session)
        assert "home" not in result

    def test_nested_session_path_collapsed(self, tmp_path):
        from app.utils.path_utils import resolve_path
        session = str(tmp_path / "session_001")
        Path(session).mkdir(parents=True)
        nested = str(tmp_path / "session_001" / "session_001" / "file.md")
        Path(nested).parent.mkdir(parents=True)
        Path(nested).write_text("test")
        result = resolve_path(nested, session)
        parts = Path(result).parts
        assert parts.count("session_001") == 1

    def test_absolute_path_outside_session_uses_filename_only(self, tmp_path):
        from app.utils.path_utils import resolve_path
        session = str(tmp_path / "session_001")
        outside = str(tmp_path / "other" / "file.md")
        Path(session).mkdir(parents=True)
        Path(outside).parent.mkdir(parents=True)
        Path(outside).write_text("test")
        result = resolve_path(outside, session)
        parts = Path(result).parts
        assert "session_001" in parts
        assert parts[-1] == "file.md"

    def test_output_prefix_stripped(self, tmp_path):
        from app.utils.path_utils import resolve_path
        session = str(tmp_path / "session_001")
        Path(session).mkdir(parents=True)
        result = resolve_path("output/doc.md", session)
        parts = Path(result).parts
        assert "output" not in parts

    def test_reports_prefix_stripped(self, tmp_path):
        from app.utils.path_utils import resolve_path
        session = str(tmp_path / "session_001")
        Path(session).mkdir(parents=True)
        result = resolve_path("reports/doc.md", session)
        parts = Path(result).parts
        assert "reports" not in parts

    def test_session_name_in_path_stripped(self, tmp_path):
        from app.utils.path_utils import resolve_path
        session = str(tmp_path / "session_001")
        Path(session).mkdir(parents=True)
        result = resolve_path("session_001/doc.md", session)
        assert Path(result).name == "doc.md"
