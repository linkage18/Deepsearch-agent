"""
Tests for database tool security validations.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.db_tools import _validate_readonly_sql, _strip_sql_comments, _quote_identifier


class TestValidateReadonlySql:
    def test_select_passes(self):
        assert _validate_readonly_sql("SELECT * FROM papers")[0]

    def test_show_passes(self):
        assert _validate_readonly_sql("SHOW TABLES")[0]

    def test_describe_passes(self):
        assert _validate_readonly_sql("DESCRIBE papers")[0]

    def test_explain_passes(self):
        assert _validate_readonly_sql("EXPLAIN SELECT * FROM papers")[0]

    def test_multi_statement_rejected(self):
        valid, msg = _validate_readonly_sql("SELECT 1; DROP TABLE papers")
        assert not valid
        assert "多语句" in msg

    def test_mutation_rejected(self):
        assert not _validate_readonly_sql("INSERT INTO papers VALUES (1)")[0]
        assert not _validate_readonly_sql("UPDATE papers SET title='x'")[0]
        assert not _validate_readonly_sql("DELETE FROM papers")[0]
        assert not _validate_readonly_sql("DROP TABLE papers")[0]
        assert not _validate_readonly_sql("ALTER TABLE papers ADD COLUMN x")[0]
        assert not _validate_readonly_sql("TRUNCATE TABLE papers")[0]
        assert not _validate_readonly_sql("CREATE TABLE x (id INT)")[0]
        assert not _validate_readonly_sql("GRANT SELECT ON papers TO user")[0]
        assert not _validate_readonly_sql("REVOKE SELECT ON papers FROM user")[0]

    def test_comment_stripped_before_validation(self):
        """Comments should be stripped before checking the SQL prefix."""
        valid, cleaned = _validate_readonly_sql("-- comment\nSELECT * FROM papers")
        assert valid
        assert cleaned == "SELECT * FROM papers"

    def test_block_comment_stripped(self):
        valid, cleaned = _validate_readonly_sql("/* block */ SELECT 1")
        assert valid
        assert "1" in cleaned

    def test_inline_comment_stripped(self):
        """Hash comments should be stripped."""
        valid, cleaned = _validate_readonly_sql("# comment\nSELECT 1")
        assert valid

    def test_empty_sql_rejected(self):
        assert not _validate_readonly_sql("")[0]
        assert not _validate_readonly_sql("   ")[0]

    def test_with_cte(self):
        """WITH clause should be allowed (it's read-only)."""
        assert _validate_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x")[0]

    def test_mutation_in_with_block_rejected(self):
        """Even with WITH, DDL/DML should be rejected by keyword filter."""
        assert not _validate_readonly_sql("WITH x AS (SELECT 1) DELETE FROM papers")[0]


class TestStripSqlComments:
    def test_block_comment(self):
        assert _strip_sql_comments("/* comment */ SELECT 1") == "SELECT 1"

    def test_line_comment(self):
        assert _strip_sql_comments("-- line\nSELECT 1") == "SELECT 1"

    def test_hash_comment(self):
        assert _strip_sql_comments("# hash\nSELECT 1") == "SELECT 1"


class TestQuoteIdentifier:
    def test_simple(self):
        assert _quote_identifier("papers") == "`papers`"

    def test_with_underscore(self):
        assert _quote_identifier("paper_authors") == "`paper_authors`"

    def test_with_chinese(self):
        assert "`" in _quote_identifier("论文表")

    def test_invalid_chars_raises(self):
        with pytest.raises(ValueError):
            _quote_identifier("papers; DROP")

    def test_backtick_escaping(self):
        result = _quote_identifier("table_name")
        assert result == "`table_name`"


if __name__ == "__main__":
    pytest.main([__file__])
