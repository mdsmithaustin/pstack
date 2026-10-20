"""Local Git regressions for the retained workspace and diff contracts.

Expected file bytes, commit histories and refusal side effects come from the
fixtures below and workspace's public checkout/overlay/harvest contracts.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import workspace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "oracles"))
from shared import OracleError, apply_diff


UPSTREAM = {
    'app/orders.py': 'def place(order):\n    return order\n',
    'app/legacy.py': 'OLD = 1\n',
    'README.md': '# Shop\n',
    'skills/tools/SKILL.md': '# Tools\n',
}


CONTEXT = b'# Orders\n\nAmendment: a change to a placed order.\n'


def git(cwd, *args):
    env = {
        **os.environ, **workspace.GIT_ENV,
        'GIT_AUTHOR_NAME': 'Shop', 'GIT_AUTHOR_EMAIL': 'shop@example.com',
        'GIT_COMMITTER_NAME': 'Shop', 'GIT_COMMITTER_EMAIL': 'shop@example.com',
        'GIT_AUTHOR_DATE': '2026-01-01T00:00:00Z',
        'GIT_COMMITTER_DATE': '2026-01-01T00:00:00Z',
    }
    return subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


class ShopRepo(unittest.TestCase):
    """A tiny upstream repo with a pinned commit in a mirror under a private cache."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        upstream = self.base / 'upstream'
        for path, text in UPSTREAM.items():
            (upstream / path).parent.mkdir(parents=True, exist_ok=True)
            (upstream / path).write_text(text)
        git(upstream, 'init', '-q')
        git(upstream, 'add', '-A')
        git(upstream, 'commit', '-q', '-m', 'Shop')
        self.commit = git(upstream, 'rev-parse', 'HEAD').strip()
        environment = {'CANON_CACHE': str(self.base / 'cache')}
        patch = mock.patch.dict(os.environ, environment)
        patch.start()
        self.addCleanup(patch.stop)
        self.mirror = workspace.fetch('shop', self.commit, upstream)
        self.spec = workspace.Spec('shop', self.commit, {'CONTEXT.md': CONTEXT})

    def harness_workspace(self, name, skill_text):
        root = self.base / name
        (root / 'skills' / 'pstack' / 'poteto-mode').mkdir(parents=True)
        (root / 'skills' / 'pstack' / 'poteto-mode' / 'SKILL.md').write_text(skill_text)
        return root


class MaterializeTests(ShopRepo):

    def test_reference_checkout_reuses_the_cache_and_separates_overlays(self):
        checkout, tree = workspace.reference_checkout(self.spec)
        self.assertEqual(workspace.reference_checkout(self.spec), (checkout, tree))
        other, other_tree = workspace.reference_checkout(
            workspace.Spec('shop', self.commit, {'CONTEXT.md': b'Other context\n'}))
        self.assertNotEqual(other, checkout)
        self.assertNotEqual(other_tree, tree)
        self.assertEqual((checkout / 'CONTEXT.md').read_bytes(), CONTEXT)
        self.assertEqual((other / 'CONTEXT.md').read_bytes(), b'Other context\n')
        self.assertEqual(git(checkout, 'rev-parse', 'HEAD').strip(), self.commit)
        self.assertEqual(git(checkout, 'show', f'{tree}:CONTEXT.md').encode(), CONTEXT)

    def test_missing_mirror_is_refused_without_creating_a_checkout(self):
        with self.assertRaisesRegex(workspace.WorkspaceError, 'lacks'):
            workspace.reference_checkout(workspace.Spec('absent', self.commit, {}))
        self.assertFalse((workspace.cache_root() / 'checkouts').exists())

    def test_overlay_cannot_overwrite_a_mounted_skill(self):
        root = self.harness_workspace('overlay-clash', 'mounted\n')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'would overwrite mounted files'):
            workspace.materialize(root, self.mirror, self.commit,
                                  {'skills/pstack/poteto-mode/SKILL.md': b'replaced\n'})
        self.assertEqual((root / 'skills/pstack/poteto-mode/SKILL.md').read_text(), 'mounted\n')

    def test_both_arms_get_the_same_tree_with_the_overlay_applied(self):
        current = self.harness_workspace('current', '# Poteto mode\n')
        amended = self.harness_workspace('amended', '# Poteto mode\nOne more rule.\n')
        trees = [workspace.materialize(root, self.mirror, self.commit, self.spec.overlay) for root in (current, amended)]
        self.assertEqual(trees[0], trees[1])
        self.assertEqual(trees[0], workspace.reference_checkout(self.spec)[1])
        for root in (current, amended):
            self.assertEqual((root / 'CONTEXT.md').read_bytes(), CONTEXT)
            self.assertEqual((root / 'app' / 'orders.py').read_text(), UPSTREAM['app/orders.py'])
            self.assertEqual(git(root, 'status', '--porcelain'), '?? CONTEXT.md\n')

    def test_a_worktree_the_agent_adds_under_the_checkout_stays_out_of_the_harvest(self):
        root = self.harness_workspace('nested', '# Poteto mode\n')
        tree = workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)
        git(root, 'worktree', 'add', '-q', '--detach', '.worktrees/x')
        (root / '.worktrees' / 'x' / 'README.md').write_text('# Shop\nDelegate edit.\n')
        self.assertEqual(workspace.harvest(root, tree), b'')

    def test_repo_file_where_a_mounted_file_sits_is_refused(self):
        root = self.harness_workspace('clash', '# Poteto mode\n')
        (root / 'README.md').write_text('mounted\n')
        with self.assertRaisesRegex(workspace.WorkspaceError, "would overwrite mounted files: \\['README.md'\\]"):
            workspace.materialize(root, self.mirror, self.commit, {})


class HistoryRepo(ShopRepo):
    """The pinned commit sits one commit above the root commit."""

    def setUp(self):
        super().setUp()
        upstream = self.base / 'upstream'
        (upstream / 'app' / 'legacy.py').write_text('OLD = 2\n')
        git(upstream, 'commit', '-qam', 'Keep legacy orders readable (#12)')
        self.head = git(upstream, 'rev-parse', 'HEAD').strip()
        self.upstream = upstream

    def log(self, root):
        return git(root, 'log', '--format=%s')


class HistoryTests(HistoryRepo):
    """A history case sees both commits, and every other case sees only the
    pinned commit."""

    def test_reference_checkout_preserves_requested_history_and_overlay(self):
        workspace.fetch('shop', self.head, self.upstream, history=True)
        workspace.fetch('shop', self.head, self.upstream)
        full, _ = workspace.reference_checkout(
            workspace.Spec('shop', self.head, {'CONTEXT.md': CONTEXT}, history=True))
        shallow, _ = workspace.reference_checkout(workspace.Spec('shop', self.head, {}))
        self.assertNotEqual(full, shallow)
        self.assertEqual(self.log(full), 'Keep legacy orders readable (#12)\nShop\n')
        self.assertEqual(self.log(shallow), 'Keep legacy orders readable (#12)\n')
        self.assertEqual((full / 'CONTEXT.md').read_bytes(), CONTEXT)
        self.assertEqual((full / 'app/legacy.py').read_text(), 'OLD = 2\n')

    def test_history_case_sees_every_ancestor_of_the_pinned_commit(self):
        mirror = workspace.fetch('shop', self.head, self.upstream, history=True)
        root = self.harness_workspace('history', '# Poteto mode\n')
        workspace.materialize(root, mirror, self.head, {}, history=True)
        self.assertEqual(self.log(root), 'Keep legacy orders readable (#12)\nShop\n')

    def test_history_fetch_leaves_the_depth_one_mirror_alone(self):
        shallow = (self.mirror / 'shallow').read_text()
        mirror = workspace.fetch('shop', self.head, self.upstream, history=True)
        self.assertEqual((mirror.name, (self.mirror / 'shallow').read_text()), ('shop.history.git', shallow))
        self.assertFalse(workspace.has_commit(self.mirror, self.head))

    def test_other_cases_see_only_the_pinned_commit_even_from_a_full_mirror(self):
        mirror = workspace.fetch('shop', self.head, self.upstream, history=True)
        root = self.harness_workspace('pinned', '# Poteto mode\n')
        workspace.materialize(root, mirror, self.head, {})
        self.assertEqual(self.log(root), 'Keep legacy orders readable (#12)\n')

    def test_history_case_refuses_a_mirror_that_holds_only_the_pinned_commit(self):
        mirror = workspace.fetch('shop', self.head, self.upstream)
        root = self.harness_workspace('shallow', '# Poteto mode\n')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'lacks the history of'):
            workspace.materialize(root, mirror, self.head, {}, history=True)

    def test_spec_reads_the_history_flag(self):
        spec = workspace.parse_spec(self.base, {'repo': 'shop', 'commit': self.head, 'history': True})
        self.assertEqual((spec.history, workspace.parse_spec(self.base, {'repo': 'shop', 'commit': self.head}).history), (True, False))
        with self.assertRaisesRegex(workspace.WorkspaceError, 'history must be true or absent'):
            workspace.parse_spec(self.base, {'repo': 'shop', 'commit': self.head, 'history': 'yes'})


class OverlayWriteTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.root, self.host = (self.base / 'checkout', self.base / 'host')
        self.root.mkdir()
        self.host.mkdir()

    def test_overlay_under_a_symlinked_directory_is_refused_and_nothing_is_written_outside(self):
        (self.root / 'escape').symlink_to(self.host)
        with self.assertRaisesRegex(workspace.WorkspaceError, '^overlay path escape/payload.txt passes through a symlink in the checkout$'):
            workspace.write_overlay(self.root, {'escape/payload.txt': b'x'})
        self.assertEqual(list(self.host.iterdir()), [])

    def test_overlay_onto_a_symlinked_file_is_refused(self):
        (self.host / 'target.txt').write_text('host\n')
        (self.root / 'CONTEXT.md').symlink_to(self.host / 'target.txt')
        with self.assertRaisesRegex(workspace.WorkspaceError, '^overlay path CONTEXT.md passes through a symlink in the checkout$'):
            workspace.write_overlay(self.root, {'CONTEXT.md': b'x'})
        self.assertEqual((self.host / 'target.txt').read_text(), 'host\n')

    def test_overlay_writes_new_and_existing_paths_under_the_checkout(self):
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'a.md').write_text('old\n')
        workspace.write_overlay(self.root, {'docs/a.md': b'new\n', 'notes/b.md': b'b\n'})
        self.assertEqual(((self.root / 'docs' / 'a.md').read_text(), (self.root / 'notes' / 'b.md').read_text()), ('new\n', 'b\n'))

    def test_all_overlay_paths_are_validated_before_any_write(self):
        (self.root / 'escape').symlink_to(self.host)
        with self.assertRaises(workspace.WorkspaceError):
            workspace.write_overlay(self.root, {'first.txt': b'first', 'escape/last.txt': b'last'})
        self.assertFalse((self.root / 'first.txt').exists())
        self.assertEqual(list(self.host.iterdir()), [])


class SpecKeyTests(unittest.TestCase):

    def test_overlay_order_is_irrelevant_but_contents_and_paths_are_distinct(self):
        first = workspace.Spec('shop', 'a' * 40, {'a': b'one', 'b': b'two'})
        reordered = workspace.Spec('shop', 'a' * 40, {'b': b'two', 'a': b'one'})
        self.assertEqual(first.key, reordered.key)
        for spec in (workspace.Spec('other', 'a' * 40, first.overlay),
                     workspace.Spec('shop', 'b' * 40, first.overlay),
                     workspace.Spec('shop', 'a' * 40, {'a': b'two', 'b': b'one'}),
                     workspace.Spec('shop', 'a' * 40, {'a': b'one', 'c': b'two'})):
            with self.subTest(spec=spec):
                self.assertNotEqual(first.key, spec.key)

    def test_a_history_checkout_gets_its_own_cache_key_and_others_keep_theirs(self):
        plain = workspace.Spec('hermes', 'a' * 40, {})
        self.assertNotEqual(workspace.Spec('hermes', 'a' * 40, {}, history=True).key, plain.key)
        self.assertEqual(plain.key, 'hermes-aaaaaaaaaaaa-ec04279dd948')


class ParseSpecTests(unittest.TestCase):

    def test_invalid_specs_are_refused(self):
        valid = {'repo': 'shop', 'commit': 'a' * 40}
        invalid = [None, {}, {'repo': 'shop'}, {**valid, 'extra': True},
                   {**valid, 'repo': '../shop'}, {**valid, 'repo': 42},
                   {**valid, 'commit': 'a' * 39}, {**valid, 'commit': 42}]
        invalid.extend({**valid, 'history': value} for value in (False, None, 1, 'yes'))
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(workspace.WorkspaceError):
                workspace.parse_spec(ROOT, raw)

    def test_overlay_must_be_a_directory_inside_the_case(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = Path(directory)
            case = base / 'case'
            case.mkdir()
            (base / 'outside').mkdir()
            (case / 'file').write_text('not a directory\n')
            (case / 'escape').symlink_to(base / 'outside')
            for overlay in ('../outside', 'escape', 'missing', 'file'):
                with self.subTest(overlay=overlay), self.assertRaises(workspace.WorkspaceError):
                    workspace.parse_spec(case, {'repo': 'shop', 'commit': 'a' * 40,
                                                'overlay': overlay})

    def test_overlay_symlink_to_a_host_file_is_not_read(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        (base / 'secret.txt').write_text('host secret\n')
        overlay = base / 'case' / 'overlay'
        overlay.mkdir(parents=True)
        (overlay / 'CONTEXT.md').write_bytes(CONTEXT)
        (overlay / 'leak.txt').symlink_to(base / 'secret.txt')
        spec = workspace.parse_spec(base / 'case', {'repo': 'shop', 'commit': 'a' * 40, 'overlay': 'overlay/'})
        self.assertEqual(spec.overlay, {'CONTEXT.md': CONTEXT})


class ApplyDiffTests(unittest.TestCase):

    def test_empty_and_unapplicable_diffs_leave_the_checkout_untouched(self):
        self.assertEqual(apply_diff(self.checkout, ''), {})
        diff = ('--- a/app/orders.py\n+++ b/app/orders.py\n'
                '@@ -1 +1 @@\n-NOT THE ORIGINAL\n+replacement\n')
        with self.assertRaisesRegex(OracleError, 'does not apply'):
            apply_diff(self.checkout, diff)
        self.assertEqual((self.checkout / 'app/orders.py').read_bytes(), b'OLD = 1\n')

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(shutil.rmtree, self.base)
        self.checkout = self.base / 'checkout'
        (self.checkout / 'app').mkdir(parents=True)
        (self.checkout / 'app' / 'orders.py').write_text('OLD = 1\n')
        self.secret = self.base / 'host-secret.txt'
        self.secret.write_text('SECRET-HOST-CONTENT\n')

    def test_diff_that_adds_a_symlink_to_a_host_file_is_refused(self):
        plain = 'diff --git a/leak.txt b/leak.txt\nnew file mode 100644\n--- /dev/null\n+++ b/leak.txt\n@@ -0,0 +1 @@\n+not a link\n'
        link = f'diff --git a/leak.txt b/leak.txt\nnew file mode 120000\n--- /dev/null\n+++ b/leak.txt\n@@ -0,0 +1 @@\n+{self.secret}\n\\ No newline at end of file\n'
        self.assertEqual(apply_diff(self.checkout, plain), {'leak.txt': b'not a link\n'})
        with self.assertRaisesRegex(OracleError, '^workspace diff leaves a symlink at leak.txt$'):
            apply_diff(self.checkout, link)

    def test_diff_that_edits_a_symlink_in_the_checkout_is_refused(self):
        (self.checkout / 'app' / 'alias.py').symlink_to('orders.py')
        edit = 'diff --git a/app/{0} b/app/{0}\n--- a/app/{0}\n+++ b/app/{0}\n@@ -1 +1 @@\n-OLD = 1\n+NEW = 2\n'
        self.assertEqual(apply_diff(self.checkout, edit.format('orders.py')), {'app/orders.py': b'NEW = 2\n'})
        with self.assertRaisesRegex(OracleError, '^workspace diff touches a symlink in the checkout: app/alias.py$'):
            apply_diff(self.checkout, edit.format('alias.py'))

    def test_path_that_resolves_outside_the_checkout_is_refused(self):
        (self.checkout / 'docs').symlink_to(self.base)
        edit = 'diff --git a/docs/host-secret.txt b/docs/host-secret.txt\n--- a/docs/host-secret.txt\n+++ b/docs/host-secret.txt\n@@ -1 +1 @@\n-SECRET-HOST-CONTENT\n+changed\n'
        with self.assertRaisesRegex(OracleError, '^workspace diff path resolves outside the checkout: docs/host-secret.txt$'):
            apply_diff(self.checkout, edit)


class DiffRoundTripTests(ShopRepo):
    def test_edits_additions_deletions_and_renames_apply_without_mutating_reference(self):
        root = self.harness_workspace('run', 'mounted\n')
        tree = workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)
        checkout, _ = workspace.reference_checkout(self.spec)
        index_before = (root / '.git/index').read_bytes()
        (root / 'app/orders.py').write_bytes(b'NEW = 2\n')
        (root / 'app/legacy.py').unlink()
        (root / 'README.md').rename(root / 'Renamed.md')
        (root / 'new.bin').write_bytes(b'\x00\xff\x01new\n')
        (root / 'CONTEXT.md').write_bytes(b'Updated context\n')
        (root / 'skills/pstack/poteto-mode/SKILL.md').write_text('changed mount\n')

        diff = workspace.harvest(root, tree).decode('utf-8', 'surrogateescape')
        self.assertEqual(apply_diff(checkout, diff), {
            'app/orders.py': b'NEW = 2\n', 'app/legacy.py': None,
            'README.md': None, 'Renamed.md': b'# Shop\n',
            'new.bin': b'\x00\xff\x01new\n', 'CONTEXT.md': b'Updated context\n',
        })
        self.assertEqual((root / '.git/index').read_bytes(), index_before)
        for path, text in UPSTREAM.items():
            self.assertEqual((checkout / path).read_bytes(), text.encode())
        self.assertEqual((checkout / 'CONTEXT.md').read_bytes(), CONTEXT)
        self.assertFalse((checkout / 'new.bin').exists())
        self.assertFalse((checkout / 'Renamed.md').exists())

    def test_unchanged_checkout_has_no_harvested_changes(self):
        root = self.harness_workspace('idle', 'mounted\n')
        tree = workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)
        self.assertEqual(workspace.harvest(root, tree), b'')


if __name__ == '__main__':
    unittest.main()
