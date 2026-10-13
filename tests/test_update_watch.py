import gzip
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from update_watch import news, shells
from update_watch.backends.arch import ArchBackend
from update_watch.backends.debian import DebianBackend
from update_watch.backends.fedora import FedoraBackend
from update_watch.distro import detect_family
from update_watch.estimate import estimate_seconds
from update_watch.util import human_duration, human_size, parse_size

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    return os.path.join(FIXTURES, name)


class ArchTest(unittest.TestCase):
    def setUp(self):
        self.b = ArchBackend(log_path=fixture("pacman.log"))

    def test_last_upgrade_skips_noop_and_partial_upgrades(self):
        last = self.b.last_upgrade()
        self.assertEqual(last, datetime(2026, 10, 9, 21, 59, 55, tzinfo=timezone(timedelta(hours=5, minutes=30))))

    def test_history_handles_mixed_offsets(self):
        self.assertEqual(self.b.history(), [(2, 240.0), (3, 63.0)])

    def test_missing_log(self):
        self.assertIsNone(ArchBackend(log_path="/nonexistent").last_upgrade())


class DebianTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        shutil.copy(fixture("apt-history.log"), os.path.join(self.dir, "history.log"))
        with gzip.open(os.path.join(self.dir, "history.log.1.gz"), "wt") as f:
            f.write("Start-Date: 2026-09-01  10:00:00\nCommandline: apt upgrade\n"
                    "Upgrade: a:amd64 (1, 2), b:amd64 (1, 2)\nEnd-Date: 2026-09-01  10:01:00\n")
        self.b = DebianBackend(log_dir=self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_last_upgrade_counts_unattended_but_not_installs(self):
        last = self.b.last_upgrade()
        self.assertEqual(last.replace(tzinfo=None), datetime(2026, 10, 6, 7, 0, 20))

    def test_history_includes_rotated_logs(self):
        self.assertEqual(self.b.history(), [(2, 60.0), (3, 90.0), (1, 20.0)])


def make_dnf4_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE trans (id INTEGER PRIMARY KEY, dt_begin INTEGER, dt_end INTEGER, cmdline TEXT, state INTEGER);
        CREATE TABLE trans_item (id INTEGER PRIMARY KEY, trans_id INTEGER, item_id INTEGER, action INTEGER);
        INSERT INTO trans VALUES (1, 1790000000, 1790000100, 'dnf upgrade', 1);
        INSERT INTO trans VALUES (2, 1790500000, 1790500010, 'dnf install htop', 1);
        INSERT INTO trans VALUES (3, 1790600000, 1790600030, '', 1);
    """)
    con.executemany("INSERT INTO trans_item (trans_id, item_id, action) VALUES (?, ?, ?)",
                    [(1, i, 6) for i in range(4)] + [(2, 9, 1), (2, 10, 6)] + [(3, i, 6) for i in range(6)])
    con.commit()
    con.close()


def make_dnf5_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE trans (id INTEGER PRIMARY KEY, dt_begin INTEGER, dt_end INTEGER, description TEXT);
        CREATE TABLE trans_item_action (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE trans_item (id INTEGER PRIMARY KEY, trans_id INTEGER, item_id INTEGER, action_id INTEGER);
        INSERT INTO trans_item_action VALUES (1, 'Install'), (2, 'Upgrade'), (3, 'Upgraded');
        INSERT INTO trans VALUES (1, 1790700000, 1790700050, 'dnf5 upgrade --refresh');
    """)
    con.executemany("INSERT INTO trans_item (trans_id, item_id, action_id) VALUES (?, ?, ?)",
                    [(1, 1, 2), (1, 2, 2), (1, 3, 3)])
    con.commit()
    con.close()


class FedoraTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.dnf4, self.dnf5 = os.path.join(self.dir, "h4.sqlite"), os.path.join(self.dir, "h5.sqlite")
        make_dnf4_db(self.dnf4)
        make_dnf5_db(self.dnf5)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_merges_dnf4_and_dnf5_and_skips_installs(self):
        b = FedoraBackend(db_paths=(self.dnf5, self.dnf4))
        self.assertEqual(b.history(), [(4, 100.0), (6, 30.0), (2, 50.0)])
        self.assertEqual(b.last_upgrade(), datetime.fromtimestamp(1790700050, timezone.utc))

    def test_missing_db(self):
        self.assertIsNone(FedoraBackend(db_paths=("/nonexistent",)).last_upgrade())


class NewsTest(unittest.TestCase):
    def parse(self, name, **kw):
        with open(fixture(name), "rb") as f:
            return news.parse_feed(f.read(), "Test", **kw)

    def test_rss2(self):
        items = self.parse("rss2.xml")
        self.assertEqual([i["title"] for i in items],
                         ["Mkinitcpio >=42 requires manual intervention", "New Arch wiki theme"])
        self.assertEqual([i["important"] for i in items], [True, False])

    def test_rdf_and_atom(self):
        rdf = self.parse("rdf.xml")
        self.assertEqual(rdf[0]["link"], "https://www.debian.org/News/2026/20260906")
        atom = self.parse("atom.xml")
        self.assertEqual(atom[0]["link"], "https://example.com/a")
        self.assertTrue(atom[0]["important"])

    def test_flag_all(self):
        self.assertTrue(all(i["important"] for i in self.parse("rss2.xml", flag_all=True)))

    def test_default_feeds(self):
        keys = lambda info: [f["key"] for f in news.default_feeds(info)]
        self.assertEqual(keys({"ID": "cachyos", "ID_LIKE": "arch"}), ["arch", "cachyos", "cachyos-forum"])
        self.assertEqual(keys({"ID": "linuxmint", "ID_LIKE": "ubuntu debian"}), ["mint", "ubuntu"])
        self.assertEqual(keys({"ID": "pop", "ID_LIKE": "ubuntu debian"}), ["ubuntu"])
        self.assertEqual(keys({"ID": "fedora"}), ["fedora", "fedora-issues"])
        self.assertEqual(keys({"ID": "rocky", "ID_LIKE": "rhel centos fedora"}), ["fedora", "fedora-issues"])


class DistroTest(unittest.TestCase):
    def test_families(self):
        self.assertEqual(detect_family({"ID": "cachyos", "ID_LIKE": "arch"}), "arch")
        self.assertEqual(detect_family({"ID": "manjaro", "ID_LIKE": "arch"}), "arch")
        self.assertEqual(detect_family({"ID": "pop", "ID_LIKE": "ubuntu debian"}), "debian")
        self.assertEqual(detect_family({"ID": "fedora"}), "fedora")
        self.assertEqual(detect_family({"ID": "almalinux", "ID_LIKE": "rhel centos fedora"}), "fedora")


class EstimateTest(unittest.TestCase):
    def test_uses_median_rate_and_ignores_outliers(self):
        history = [(10, 50), (10, 100), (10, 60), (5, 99999)]
        self.assertEqual(estimate_seconds(history, 20, 0, True, 10), 120)

    def test_adds_download_when_history_excludes_it(self):
        self.assertEqual(estimate_seconds([(10, 100)], 10, 50e6, False, 10), 105)
        self.assertEqual(estimate_seconds([(10, 100)], 10, 50e6, True, 10), 100)

    def test_fallback_without_history(self):
        self.assertEqual(estimate_seconds([], 30, 10e6, True, 10), 61)

    def test_formatting(self):
        self.assertEqual(human_duration(20), "<1 min")
        self.assertEqual(human_duration(370), "~6 min")
        self.assertEqual(human_duration(4000), "~1 h 7 min")
        self.assertEqual(human_size(412_000_000), "412 MB")
        self.assertEqual(human_size(-3_400_000), "-3.4 MB")
        self.assertEqual(parse_size("9.05 MiB"), int(9.05 * 1024 ** 2))


class ShellsTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.patches = [mock.patch.object(shells, "HOME", self.home),
                        mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(self.home, ".config")})]
        for p in self.patches:
            p.start()
        os.environ.pop("ZDOTDIR", None)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.home)

    def test_bash_install_is_idempotent_and_reversible(self):
        rc = os.path.join(self.home, ".bashrc")
        original = "alias ll='ls -l'\nexport EDITOR=vim\n"
        with open(rc, "w") as f:
            f.write(original)
        shells.install("bash")
        shells.install("bash")
        with open(rc) as f:
            self.assertEqual(f.read().count(shells.BEGIN), 1)
        shells.uninstall("bash")
        with open(rc) as f:
            self.assertEqual(f.read(), original)

    def test_zsh_creates_rc(self):
        shells.install("zsh")
        self.assertTrue(shells.is_installed("zsh"))

    def test_fish_replaces_symlink(self):
        path = shells.rc_path("fish")
        os.makedirs(os.path.dirname(path))
        target = os.path.join(self.home, "repo-file.fish")
        with open(target, "w") as f:
            f.write("old")
        os.symlink(target, path)
        shells.install("fish")
        self.assertFalse(os.path.islink(path))
        with open(target) as f:
            self.assertEqual(f.read(), "old")
        shells.uninstall("fish")
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
