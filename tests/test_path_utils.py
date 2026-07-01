"""
Tests for path resolution and traversal prevention.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.path_utils import resolve_path, _is_relative_to, _fix_nested_session_path


class TestResolvePath:
    def test_rejects_traversal(self, tmp_path):
        session_dir = tmp_path / "session_safe"
        session_dir.mkdir()
        with pytest.raises(ValueError, match="拒绝访问"):
            resolve_path("../../outside.txt", str(session_dir))

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="不能为空"):
            resolve_path("")
        with pytest.raises(ValueError, match="不能为空"):
            resolve_path("   ")

    def test_strips_virtual_prefixes(self, tmp_path):
        """/workspace, /mnt/data prefixes should be stripped."""
        result = resolve_path("/workspace/output.md", str(tmp_path))
        assert str(tmp_path) in result
        assert "output.md" in result

    def test_absolute_outside_session(self, tmp_path):
        """Absolute path outside session_dir should resolve to a path within session_dir."""
        session_dir = tmp_path / "safe_session"
        session_dir.mkdir()
        # Use platform-appropriate "outside" path
        result = resolve_path(str(tmp_path / "outside.txt"), str(session_dir))
        # Should resolve to something within session_dir
        assert "outside.txt" in result
        assert "safe_session" in result

    def test_relative_in_session(self, tmp_path):
        """Relative path inside session_dir should resolve correctly."""
        session_dir = tmp_path / "session_x"
        session_dir.mkdir()
        # Creating a file inside session_dir
        f = session_dir / "myfile.md"
        f.write_text("test")
        result = resolve_path("myfile.md", str(session_dir))
        assert str(session_dir) in result
        assert "myfile.md" in result

    def test_relative_nonexistent_in_session(self, tmp_path):
        """Non-existent relative path should still resolve within session."""
        session_dir = tmp_path / "session_y"
        session_dir.mkdir()
        result = resolve_path("report.md", str(session_dir))
        assert str(session_dir) in result

    def test_output_prefix_stripped(self, tmp_path):
        """Leading output/reports/uploads/updated should be removed."""
        session_dir = tmp_path / "session_x"
        session_dir.mkdir()
        result = resolve_path("output/report.md", str(session_dir))
        assert result == str((session_dir / "report.md").resolve())

    def test_nested_session_path(self, tmp_path):
        """session_x/session_x/file.md should be deduplicated."""
        session_dir = tmp_path / "session_x"
        session_dir.mkdir()
        result = resolve_path("session_x/file.md", str(session_dir))
        assert "session_x/session_x" not in result


class TestIsRelativeTo:
    def test_child_is_relative(self, tmp_path):
        parent = tmp_path / "a" / "b"
        child = parent / "c"
        assert _is_relative_to(child, parent)

    def test_not_relative(self, tmp_path):
        a = tmp_path / "a" / "b" / "c"
        b = tmp_path / "d" / "e"
        assert not _is_relative_to(a, b)

    def test_same_path(self, tmp_path):
        assert _is_relative_to(tmp_path, tmp_path)


if __name__ == "__main__":
    pytest.main([__file__])
