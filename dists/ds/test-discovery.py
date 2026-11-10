#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Release provenance and notice tests; no SDK, network or game data required."""

import importlib.util
from pathlib import Path
import io
import subprocess
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("release", Path(__file__).with_name("prepare-release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


spec = importlib.util.spec_from_file_location("builder", Path(__file__).with_name("build-discovery.py"))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SourceProvenanceChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def init_repository(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "fixture").write_text("original\n")
        subprocess.run(["git", "add", "fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Build test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "Authored fixture"], cwd=self.root, check=True)

    def test_exported_source_has_no_release_provenance(self):
        self.assertEqual(builder.source_state(self.root), (None, True))

    def test_nested_export_does_not_inherit_parent_revision(self):
        self.init_repository()
        export = self.root / "source-export"
        export.mkdir()
        self.assertEqual(builder.source_state(export), (None, True))

    def test_clean_and_modified_checkout_provenance(self):
        self.init_repository()
        revision, dirty = builder.source_state(self.root)
        self.assertRegex(revision, r"^[0-9a-f]{40}$")
        self.assertFalse(dirty)
        (self.root / "fixture").write_text("modified\n")
        self.assertEqual(builder.source_state(self.root), (revision, True))


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.binary = self.root / "scummvm.nds"
        self.binary.write_bytes(b"authored build fixture")
        self.manifest = {"source_dirty": False, "sha256": release.sha256(self.binary),
                         "source_commit": "a" * 40, "sdk_libraries_sha256": {"lib.a": "b" * 64},
                         "arm7_sha256": "c" * 64, "compiler_runtime_sha256": {"libc.a": "d" * 64}}
        self.lock = {key: self.manifest[key] for key in
                     ("sdk_libraries_sha256", "arm7_sha256", "compiler_runtime_sha256")}

    def test_matching_provenance(self):
        release.verify_build(self.manifest, self.binary, self.lock)

    def test_dirty_source_is_rejected(self):
        with self.assertRaises(ValueError):
            release.verify_build({**self.manifest, "source_dirty": True}, self.binary, self.lock)

    def test_changed_binary_is_rejected(self):
        self.binary.write_bytes(b"stale manifest")
        with self.assertRaises(ValueError):
            release.verify_build(self.manifest, self.binary, self.lock)

    def test_changed_sdk_is_rejected(self):
        for key in ("sdk_libraries_sha256", "arm7_sha256", "compiler_runtime_sha256"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                release.verify_build({**self.manifest, key: "different"}, self.binary, self.lock)

    def test_unsafe_archive_names_are_rejected(self):
        for name in ("", "../outside", "/absolute", "dir/../../outside", "bad\\path"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.safe_path(name)

    def test_cached_download_still_requires_its_checksum(self):
        with self.assertRaises(ValueError):
            release.download("https://unused.invalid", self.binary, "0" * 64)

    def test_sdk_notices_and_copyright_headers_are_kept(self):
        archive = self.root / "sdk.tar.gz"
        inputs = {"sdk/COPYING": b"Complete authored license fixture\n",
                  "sdk/source.c": b"/* Copyright Example Authors. Keep this notice. */\nint fixture;\n"}
        with tarfile.open(archive, "w:gz") as target:
            for name, data in inputs.items():
                item = tarfile.TarInfo(name)
                item.size = len(data)
                target.addfile(item, io.BytesIO(data))
        notices = release.sdk_notices(archive)
        self.assertEqual(notices["sdk/COPYING"], inputs["sdk/COPYING"])
        self.assertIn(b"Copyright Example Authors", b"\n".join(notices.values()))


if __name__ == "__main__":
    unittest.main()
