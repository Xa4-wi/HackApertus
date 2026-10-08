import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prepare_submission", Path(__file__).parents[1] / "scripts/prepare_submission.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class SubmissionPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "track_2a/src/app.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("print('application')\n")
        (self.root / "track_2a/scripts").mkdir()
        (self.root / "track_2a/scripts/build_submission_report.py").write_text("# report builder\n")
        (self.root / "track_2a/technical_report.md").write_text("# Final report\n")
        self.allowlist = self.root / "track_2a/submission-files.txt"
        self.allowlist.write_text("# Explicit source files\ntrack_2a/src/app.py\n")
        self.submission = self.root / "submission"
        self.submission.mkdir()
        self.pdf = self.submission / "technical_report.pdf"
        self.pdf.write_bytes(b"report fixture")
        self.build_path = self.pdf.with_suffix(".build.json")
        self.review_path = self.pdf.with_suffix(".visual-review.json")
        self.refresh_report_metadata()

    def write_json(self, path, value):
        path.write_text(json.dumps(value))

    def refresh_report_metadata(self):
        self.build = {"source_sha256": package.digest((self.root / "track_2a/technical_report.md").read_bytes()),
            "builder_sha256": package.digest((self.root / "track_2a/scripts/build_submission_report.py").read_bytes()),
            "pdf_sha256": package.digest(self.pdf.read_bytes()), "pages": 2}
        self.review = {"verdict": "pass", "source_sha256": self.build["source_sha256"],
            "pdf_sha256": self.build["pdf_sha256"], "pages": 2, "pages_visually_reviewed": [1, 2]}
        self.write_json(self.build_path, self.build)
        self.write_json(self.review_path, self.review)

    def test_allowlisted_handover_hashes_and_idempotent_regeneration(self):
        manifest = package.prepare(self.root)
        self.assertEqual(set(manifest["files"]), {"project/README.md", "project/track_2a/src/app.py", "technical_report.pdf"})
        for name, expected in manifest["files"].items():
            self.assertEqual(package.digest((self.submission / name).read_bytes()), expected)
        self.assertEqual(manifest["allowlist_sha256"], package.digest(self.allowlist.read_bytes()))
        self.assertEqual(package.prepare(self.root), manifest)
        self.pdf.write_bytes(b"regenerated report fixture")
        self.refresh_report_metadata()
        updated = package.prepare(self.root)
        self.assertNotEqual(updated["files"]["technical_report.pdf"], manifest["files"]["technical_report.pdf"])

    def test_secrets_history_data_weights_and_traversal_are_rejected(self):
        excluded = (".env", "track_2a/.env.local", "archive/old.py", "VERSION_HISTORY.md",
                     "track_2a/output/result.txt", "track_2a/data/snapshot.json", "track_2a/weights/model.gguf",
                     ".git/config", "track_2a/.venv/module.py", ".local/bin/dmr", "dist/bundle.js")
        for name in excluded:
            source = self.root / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("must not be included\n")
        invalid = ("../outside.py", "/absolute.py", "track_2a//src/app.py", "track_2a/src/./app.py", "README.md")
        for name in (*excluded, *invalid):
            with self.subTest(name=name):
                self.allowlist.write_text(name + "\n")
                with self.assertRaisesRegex(ValueError, "Excluded content" if name in excluded else "Invalid allowlist"):
                    package.prepare(self.root)
                self.assertFalse((self.submission / "project").exists())
        example = self.root / "track_2a/.env.example"
        example.write_text("APERTUS_API_KEY=\n")
        self.allowlist.write_text("track_2a/.env.example\n")
        package.prepare(self.root)
        self.assertTrue((self.submission / "project/track_2a/.env.example").is_file())

    def test_duplicate_or_missing_allowlisted_sources_are_rejected(self):
        for content, message in (("track_2a/src/app.py\ntrack_2a/src/app.py\n", "Duplicate"),
                                 ("track_2a/src/missing.py\n", "missing"), ("# empty\n", "empty")):
            self.allowlist.write_text(content)
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, message):
                package.prepare(self.root)

    def test_source_and_destination_symlinks_are_rejected(self):
        link = self.source.with_name("linked.py")
        link.symlink_to(self.source)
        self.allowlist.write_text("track_2a/src/linked.py\n")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            package.prepare(self.root)
        parent_link = self.root / "track_2a/linked-src"
        parent_link.symlink_to(self.source.parent, target_is_directory=True)
        self.allowlist.write_text("track_2a/linked-src/app.py\n")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            package.prepare(self.root)
        self.allowlist.write_text("track_2a/src/app.py\n")
        (self.submission / "project").symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            package.prepare(self.root)

    def test_existing_user_changes_new_files_and_missing_files_are_preserved(self):
        package.prepare(self.root)
        staged_source = self.submission / "project/track_2a/src/app.py"
        original = staged_source.read_bytes()
        staged_source.write_text("# user edit\n")
        with self.assertRaisesRegex(ValueError, "preserve those edits"):
            package.prepare(self.root)
        self.assertEqual(staged_source.read_text(), "# user edit\n")
        staged_source.write_bytes(original)
        unexpected = staged_source.with_name("user-file.txt")
        unexpected.write_text("user content")
        with self.assertRaisesRegex(ValueError, "extended"):
            package.prepare(self.root)
        self.assertEqual(unexpected.read_text(), "user content")
        unexpected.unlink()
        staged_source.unlink()
        with self.assertRaisesRegex(ValueError, "removed"):
            package.prepare(self.root)

    def test_untracked_existing_project_and_symlinks_are_preserved(self):
        project = self.submission / "project"
        project.mkdir()
        with self.assertRaisesRegex(ValueError, "lacks its project or manifest"):
            package.prepare(self.root)
        project.rmdir()
        package.prepare(self.root)
        link = project / "private-link"
        link.symlink_to(self.root / "track_2a")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            package.prepare(self.root)
        self.assertTrue(link.is_symlink())

    def test_stale_builds_and_incomplete_visual_reviews_are_rejected(self):
        for key in ("source_sha256", "builder_sha256", "pdf_sha256"):
            with self.subTest(key=key):
                self.write_json(self.build_path, dict(self.build, **{key: "stale"}))
                with self.assertRaisesRegex(ValueError, "stale"):
                    package.prepare(self.root)
        self.write_json(self.build_path, self.build)
        for change in ({"verdict": "fail"}, {"source_sha256": "stale"}, {"pdf_sha256": "stale"},
                       {"pages": 3}, {"pages_visually_reviewed": [1]}, {"pages_visually_reviewed": [1, 1, 2]},
                       {"pages_visually_reviewed": [True, 2]}):
            with self.subTest(change=change):
                self.write_json(self.review_path, dict(self.review, **change))
                with self.assertRaisesRegex(ValueError, "visual review"):
                    package.prepare(self.root)
        self.refresh_report_metadata()
        for pages in (0, 7, True):
            self.write_json(self.build_path, dict(self.build, pages=pages))
            with self.subTest(pages=pages), self.assertRaisesRegex(ValueError, "one and six"):
                package.prepare(self.root)
        self.build_path.unlink()
        with self.assertRaises(OSError):
            package.prepare(self.root)

    def test_failed_manifest_install_restores_previous_project(self):
        original = package.prepare(self.root)
        self.source.write_text("# new application version\n")
        replace = Path.replace

        def fail_manifest(path, target):
            if Path(target).resolve() == (self.submission / "manifest.json").resolve():
                raise OSError("simulated failed manifest install")
            return replace(path, target)

        with patch.object(Path, "replace", new=fail_manifest):
            with self.assertRaisesRegex(OSError, "simulated"):
                package.prepare(self.root)
        self.assertEqual(package.project_hashes(self.submission / "project"),
            {key: value for key, value in original["files"].items() if key.startswith("project/")})
        self.assertEqual(json.loads((self.submission / "manifest.json").read_text()), original)
        self.assertFalse(list(self.submission.glob(".handover-*")))


if __name__ == "__main__":
    unittest.main()
