"""archive_database_path 解析顺序：SIRE_ARCHIVE_DB > SIRE_ARCHIVE_ROOT > 已知位置回退（文件存在才用）> None。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sire_paths  # noqa: E402


class ArchivePathTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("SIRE_ARCHIVE_DB", None)
        os.environ.pop("SIRE_ARCHIVE_ROOT", None)
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.env.stop()

    def test_explicit_db_wins(self):
        os.environ["SIRE_ARCHIVE_DB"] = str(self.tmp / "a.sqlite3")
        os.environ["SIRE_ARCHIVE_ROOT"] = str(self.tmp / "root")
        self.assertEqual(self.tmp / "a.sqlite3", sire_paths.archive_database_path())

    def test_root_used_when_no_db(self):
        os.environ["SIRE_ARCHIVE_ROOT"] = str(self.tmp)
        self.assertEqual(self.tmp / "sire_vectors.sqlite3", sire_paths.archive_database_path())

    def test_fallback_only_when_file_exists(self):
        default = self.tmp / "known.sqlite3"
        with mock.patch.object(sire_paths, "DEFAULT_ARCHIVE_DB", default):
            self.assertIsNone(sire_paths.archive_database_path())  # 文件不存在：仍返回 None，不凭空猜测
            default.write_text("x", encoding="utf-8")
            self.assertEqual(default, sire_paths.archive_database_path())

    def test_env_beats_fallback(self):
        default = self.tmp / "known.sqlite3"
        default.write_text("x", encoding="utf-8")
        os.environ["SIRE_ARCHIVE_DB"] = str(self.tmp / "env.sqlite3")
        with mock.patch.object(sire_paths, "DEFAULT_ARCHIVE_DB", default):
            self.assertEqual(self.tmp / "env.sqlite3", sire_paths.archive_database_path())


if __name__ == "__main__":
    unittest.main()
