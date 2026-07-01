"""Advanced tests for db_tools — SQL guard, query validation, edge cases."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestSqlGuard:
    def test_valid_select_passes(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("SELECT * FROM papers")
        assert ok

    def test_select_with_where(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("SELECT title, author FROM papers WHERE year > 2020")
        assert ok

    def test_show_tables_passes(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("SHOW TABLES")
        assert ok

    def test_describe_passes(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("DESCRIBE papers")
        assert ok

    def test_explain_passes(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("EXPLAIN SELECT * FROM papers")
        assert ok

    def test_with_cte_passes(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x")
        assert ok

    def test_insert_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, msg = _validate_readonly_sql("INSERT INTO papers VALUES (1)")
        assert not ok

    def test_update_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("UPDATE papers SET title='x'")
        assert not ok

    def test_delete_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("DELETE FROM papers")
        assert not ok

    def test_drop_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("DROP TABLE papers")
        assert not ok

    def test_alter_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("ALTER TABLE papers ADD COLUMN x INT")
        assert not ok

    def test_create_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("CREATE TABLE papers (id INT)")
        assert not ok

    def test_truncate_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("TRUNCATE papers")
        assert not ok

    def test_multi_statement_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("SELECT 1; DROP TABLE papers")
        assert not ok

    def test_case_insensitive_rejection(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, _ = _validate_readonly_sql("insert into papers values (1)")
        assert not ok

    def test_empty_string_rejected(self):
        from app.tools.db_tools import _validate_readonly_sql
        ok, msg = _validate_readonly_sql("")
        assert not ok


class TestDbConfig:
    def test_get_db_config_returns_dict(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "localhost")
        monkeypatch.setenv("MYSQL_USER", "test")
        monkeypatch.setenv("MYSQL_PASSWORD", "pass")
        monkeypatch.setenv("MYSQL_DATABASE", "db")
        import importlib
        from app.tools import db_tools
        importlib.reload(db_tools)
        from app.tools.db_tools import get_db_config
        config = get_db_config()
        assert config["host"] == "localhost"
        assert config["user"] == "test"

    def test_get_db_config_has_defaults(self, monkeypatch):
        monkeypatch.delenv("MYSQL_HOST", raising=False)
        monkeypatch.delenv("MYSQL_USER", raising=False)
        monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
        monkeypatch.delenv("MYSQL_DATABASE", raising=False)
        import importlib
        from app.tools import db_tools
        importlib.reload(db_tools)
        from app.tools.db_tools import get_db_config
        config = get_db_config()
        assert "host" in config
