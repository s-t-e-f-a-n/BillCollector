"""Offline contract tests for bounded Playwright collection actions."""

import copy
import os
import sys
import tempfile
import threading
import time
import unittest
import yaml
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

_REQUESTED_BROWSER_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")

from billcollector.collection import (  # noqa: E402
    CollectionError,
    click_until_absent,
    download_all,
)
from billcollector import collection as collection_module  # noqa: E402
from billcollector import recipes, runner  # noqa: E402
from billcollector.interrupt import RunInterrupted  # noqa: E402
import BillCollectorServices_pw as batch_runner  # noqa: E402


class _Events:
    def __init__(self):
        self.listeners = {}

    def on(self, name, callback):
        self.listeners.setdefault(name, []).append(callback)

    def remove_listener(self, name, callback):
        if getattr(self, "remove_error", False):
            raise RuntimeError("remove failed")
        self.listeners[name].remove(callback)

    def emit(self, name, value):
        for callback in tuple(self.listeners.get(name, [])):
            callback(value)


class _Progress:
    def __init__(self, count=0):
        self.visible = count

    def evaluate_all(self, _script):
        return self.visible


class _Pager:
    def __init__(self, page, *, pages=0, hidden=False, disabled=False,
                 stalled=False):
        self.page = page
        self.pages = pages
        self.hidden = hidden
        self.disabled = disabled
        self.stalled = stalled
        self.first = self
        self.clicks = 0

    def count(self):
        return 0 if self.pages < 0 else 1

    def is_visible(self):
        return not self.hidden

    def click(self, **_kwargs):
        if self.disabled:
            raise RuntimeError("disabled")
        self.clicks += 1
        if not self.stalled:
            self.page.progress.visible += 1
        if self.clicks >= self.pages:
            self.pages = -1


class _Page(_Events):
    def __init__(self):
        super().__init__()
        self.url = "https://example.test/list"
        self.progress = _Progress(1)
        self.back_calls = 0
        self.pending = []

    def locator(self, selector):
        if selector != ".rows":
            raise AssertionError(selector)
        return self.progress

    def wait_for_timeout(self, milliseconds):
        time.sleep(milliseconds / 1000)
        ready = [entry for entry in self.pending if entry[0] <= time.monotonic()]
        self.pending = [
            entry for entry in self.pending if entry[0] > time.monotonic()
        ]
        for _, event, value in ready:
            self.emit(event, value)

    def go_back(self, **_kwargs):
        self.back_calls += 1
        self.url = "https://example.test/list"


class PaginationTests(unittest.TestCase):
    options = {
        "progress_selector": ".rows",
        "max_clicks": 3,
        "timeout_ms": 10,
    }

    def test_initially_absent_or_hidden_is_complete(self):
        page = _Page()
        absent = _Pager(page, pages=-1)
        hidden = _Pager(page, pages=2, hidden=True)

        self.assertEqual(click_until_absent(page, absent, self.options).clicks, 0)
        self.assertEqual(click_until_absent(page, hidden, self.options).clicks, 0)

    def test_clicks_until_absent_with_required_progress(self):
        page = _Page()
        pager = _Pager(page, pages=2)

        result = click_until_absent(page, pager, self.options)

        self.assertEqual((result.clicks, result.visible_items), (2, 3))

    def test_disabled_visible_control_is_not_completion(self):
        page = _Page()
        pager = _Pager(page, pages=2, disabled=True)

        with self.assertRaisesRegex(CollectionError, "not actionable"):
            click_until_absent(page, pager, self.options)

    def test_stall_and_bound_exhaustion_fail(self):
        page = _Page()
        pager = _Pager(page, pages=2, stalled=True)
        with self.assertRaisesRegex(CollectionError, "no visible progress"):
            click_until_absent(page, pager, self.options)

        page = _Page()
        pager = _Pager(page, pages=4)
        with self.assertRaisesRegex(CollectionError, "limit reached"):
            click_until_absent(page, pager, self.options)
        self.assertEqual(pager.clicks, 3)


class _Popup(_Events):
    def __init__(self):
        super().__init__()
        self.closed = False

    def is_closed(self):
        return self.closed

    def close(self):
        if getattr(self, "close_error", False):
            raise RuntimeError("close failed")
        self.closed = True


class _Target:
    def __init__(self, listing, entry):
        self.listing = listing
        self.entry = entry
        self.disposed = False

    def evaluate(self, _script, attribute):
        return self.entry.get(attribute)

    def click(self, **kwargs):
        entry = self.entry
        self.listing.click_timeouts.append(kwargs.get("timeout"))
        self.listing.clicked.append(entry.get("data-key"))
        if entry.get("interrupt"):
            raise RunInterrupted("stop")
        if entry.get("navigate"):
            self.listing.page.url = "https://example.test/view"
        if entry.get("popup"):
            popup = _Popup()
            self.listing.context.emit("page", popup)
            popup.emit("download", entry.get("download"))
        elif entry.get("download") is not None:
            self.listing.page.emit("download", entry["download"])
        if entry.get("extra") is not None:
            self.listing.page.pending.append(
                (time.monotonic() + 0.01, "download", entry["extra"])
            )
        if entry.get("reorder"):
            self.listing.items.reverse()
        if entry.get("unstable_snapshots"):
            self.listing.unstable_snapshots = entry["unstable_snapshots"]

    def dispose(self):
        if self.entry.get("dispose_error"):
            raise RuntimeError("dispose failed")
        self.disposed = True


class _Nth:
    def __init__(self, listing, index):
        self.listing = listing
        self.index = index

    def element_handle(self, **kwargs):
        self.listing.handle_timeouts.append(kwargs.get("timeout"))
        delay = self.listing.items[self.index].get("handle_delay", 0)
        if delay:
            time.sleep(delay)
        target = _Target(self.listing, self.listing.items[self.index])
        self.listing.handles.append(target)
        return target


class _Listing:
    def __init__(self, page, context, items):
        self.page = page
        self.context = context
        self.items = items
        self.handles = []
        self.clicked = []
        self.handle_timeouts = []
        self.click_timeouts = []
        self.unstable_snapshots = 0

    def evaluate_all(self, _script, attribute):
        if self.unstable_snapshots:
            self.unstable_snapshots -= 1
            return []
        return [entry.get(attribute) for entry in self.items]

    def nth(self, index):
        return _Nth(self, index)


class DownloadAllTests(unittest.TestCase):
    options = {
        "key_attribute": "data-key",
        "max_items": 5,
        "timeout_ms": 500,
        "event_window_ms": 30,
    }

    def setup_listing(self, items):
        page = _Page()
        context = _Events()
        listing = _Listing(page, context, items)
        return page, context, listing

    def test_direct_popup_and_navigation_downloads(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one", "navigate": True},
            {"data-key": "two", "download": "two", "popup": True},
        ])
        saved = []

        records = download_all(
            page, context, listing, lambda item: saved.append(item) or item,
            self.options,
        )

        self.assertEqual(records, ["one", "two"])
        self.assertEqual(saved, ["one", "two"])
        self.assertEqual(page.back_calls, 1)
        self.assertTrue(all(handle.disposed for handle in listing.handles))

    def test_empty_duplicate_and_over_limit_fail_before_click(self):
        for items, message in (
            ([], "empty"),
            ([{"data-key": "same"}, {"data-key": "same"}], "duplicate"),
            ([{"data-key": str(i)} for i in range(6)], "recipe limit"),
        ):
            page, context, listing = self.setup_listing(items)
            with self.assertRaisesRegex(CollectionError, message):
                download_all(
                    page, context, listing, lambda item: item, self.options
                )
            self.assertEqual(listing.handles, [])

    def test_insufficient_event_budget_fails_before_any_click(self):
        page, context, listing = self.setup_listing([
            {"data-key": str(index), "download": str(index)}
            for index in range(3)
        ])
        saved = []
        with self.assertRaisesRegex(CollectionError, "must leave more than 90 ms"):
            download_all(page, context, listing, saved.append, {
                "key_attribute": "data-key",
                "max_items": 3,
                "timeout_ms": 80,
                "event_window_ms": 30,
            })
        self.assertEqual(listing.handles, [])
        self.assertEqual(saved, [])

    def test_primary_error_survives_listener_and_restoration_cleanup_failures(self):
        page, context, listing = self.setup_listing([{
            "data-key": "one", "navigate": True,
        }])
        page.remove_error = True
        page.go_back = mock.Mock(side_effect=RuntimeError("restore failed"))

        with self.assertLogs(collection_module.logger, level="WARNING") as logs:
            with self.assertRaisesRegex(CollectionError, "produced 0 files"):
                download_all(
                    page, context, listing, lambda item: item, self.options
                )

        self.assertIn("listener removal", " ".join(logs.output))
        self.assertIn("listing restoration", " ".join(logs.output))

        page, context, listing = self.setup_listing([{
            "data-key": "one", "dispose_error": True,
        }])
        with self.assertLogs(collection_module.logger, level="WARNING") as logs:
            with self.assertRaisesRegex(CollectionError, "produced 0 files"):
                download_all(
                    page, context, listing, lambda item: item, self.options
                )
        self.assertIn("element-handle disposal", " ".join(logs.output))

    def test_slow_persistence_reserves_all_remaining_event_windows(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one"},
            {"data-key": "two", "download": "two"},
        ])
        saved = []

        def save(item):
            saved.append(item)
            time.sleep(0.09)
            return item

        with self.assertRaisesRegex(CollectionError, "remaining 1 event"):
            download_all(page, context, listing, save, {
                "key_attribute": "data-key",
                "max_items": 2,
                "timeout_ms": 150,
                "event_window_ms": 40,
            })
        self.assertEqual(saved, ["one"])
        self.assertEqual(len(listing.handles), 1)

    def test_slow_list_restoration_rechecks_all_remaining_windows(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one", "unstable_snapshots": 4},
            {"data-key": "two", "download": "two"},
            {"data-key": "three", "download": "three"},
        ])
        saved = []
        with self.assertRaisesRegex(CollectionError, "remaining 2 event"):
            download_all(page, context, listing, saved.append, {
                "key_attribute": "data-key",
                "max_items": 3,
                "timeout_ms": 340,
                "event_window_ms": 50,
            })
        self.assertEqual(saved, ["one"])
        self.assertEqual(len(listing.handles), 1)

    def test_slow_handle_cannot_consume_future_event_windows(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one", "handle_delay": 0.2},
            {"data-key": "two", "download": "two"},
            {"data-key": "three", "download": "three"},
        ])
        saved = []
        with self.assertRaisesRegex(CollectionError, "remaining 3 event"):
            download_all(page, context, listing, saved.append, {
                "key_attribute": "data-key",
                "max_items": 3,
                "timeout_ms": 340,
                "event_window_ms": 50,
            })
        self.assertEqual(saved, [])
        self.assertEqual(listing.clicked, [])

    def test_positive_timeout_surplus_is_reused_without_zero_timeout(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one"},
            {"data-key": "two", "download": "two"},
            {"data-key": "three", "download": "three"},
        ])
        with mock.patch.object(
            collection_module,
            "_remaining_ms",
            side_effect=[151, 151, 151, 150],
        ):
            with self.assertRaisesRegex(CollectionError, "remaining 3 event"):
                download_all(page, context, listing, lambda item: item, {
                    "key_attribute": "data-key",
                    "max_items": 3,
                    "timeout_ms": 500,
                    "event_window_ms": 50,
                })

        self.assertEqual(listing.handle_timeouts, [1])
        self.assertEqual(listing.click_timeouts, [])
        self.assertEqual(listing.clicked, [])

    def test_changed_list_and_multiple_downloads_fail_closed(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one", "reorder": True},
            {"data-key": "two", "download": "two"},
        ])
        saved = []
        with self.assertRaisesRegex(CollectionError, "changed after 1 of 2"):
            download_all(
                page, context, listing, lambda item: saved.append(item),
                self.options,
            )
        self.assertEqual(saved, ["one"])

        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one", "extra": "two"},
        ])
        with self.assertRaisesRegex(CollectionError, "produced 2 files"):
            download_all(
                page, context, listing, lambda item: item, self.options
            )

    def test_zero_download_keeps_prior_result(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one"},
            {"data-key": "two"},
        ])
        saved = []
        with self.assertRaisesRegex(CollectionError, "produced 0 files"):
            download_all(
                page, context, listing, lambda item: saved.append(item),
                self.options,
            )
        self.assertEqual(saved, ["one"])

    def test_resume_skips_keys_persisted_before_partial_failure(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "download": "one"},
            {"data-key": "two"},
        ])
        saved = []
        completed = set()

        with self.assertRaisesRegex(CollectionError, "produced 0 files"):
            download_all(
                page,
                context,
                listing,
                lambda item: saved.append(item) or item,
                self.options,
                completed_keys=completed,
            )

        self.assertEqual(saved, ["one"])
        self.assertEqual(completed, {"one"})
        listing.items[1]["download"] = "two"

        records = download_all(
            page,
            context,
            listing,
            lambda item: saved.append(item) or item,
            self.options,
            completed_keys=completed,
        )

        self.assertEqual(records, ["two"])
        self.assertEqual(saved, ["one", "two"])
        self.assertEqual(completed, {"one", "two"})
        self.assertEqual(listing.clicked, ["one", "two", "two"])

    def test_cleanup_shutdown_overrides_primary_collection_error(self):
        page, context, listing = self.setup_listing([{
            "data-key": "one",
        }])
        page.remove_listener = mock.Mock(
            side_effect=RunInterrupted("cleanup stop")
        )

        with self.assertRaisesRegex(RunInterrupted, "cleanup stop"):
            download_all(
                page, context, listing, lambda item: item, self.options
            )

    def test_shutdown_interrupt_is_not_converted_to_collection_failure(self):
        page, context, listing = self.setup_listing([
            {"data-key": "one", "interrupt": True, "dispose_error": True},
        ])
        with self.assertRaisesRegex(RunInterrupted, "stop"):
            download_all(
                page, context, listing, lambda item: item, self.options
            )


class RecipeAndRunnerContractTests(unittest.TestCase):
    def test_schema_accepts_bounded_actions_and_rejects_unsafe_options(self):
        text = """
services:
- serviceName: sample
  steps:
  - step: 1
    methods:
    - method: locator
      arguments:
      - selector: "#more"
    - method: click_until_absent
      arguments:
      - progress_selector: ".invoice"
        max_clicks: 20
        timeout_ms: 30000
  - step: 2
    methods:
    - method: locator
      arguments:
      - selector: ".invoice"
    - method: download_all
      arguments:
      - key_attribute: href
        max_items: 200
        timeout_ms: 30000
        event_window_ms: 1000
"""
        ok, error, _ = recipes.validate_recipe(text)
        self.assertTrue(ok, error)

        for old, new in (
            ("max_clicks: 20", "max_clicks: 101"),
            ("max_items: 200", "max_items: 0"),
            ("timeout_ms: 30000", "timeout_ms: true"),
            ('progress_selector: ".invoice"', 'progress_selector: "   "'),
            ("key_attribute: href", 'key_attribute: "   "'),
            ("  - step: 1", "  - step: 1\n    graceful: true"),
            ("    - method: click_until_absent", (
                "    - method: wait_user\n"
                "    - method: click_until_absent"
            )),
            ("    - method: click_until_absent", (
                "    - method: click\n"
                "    - method: click_until_absent"
            )),
            ("    - method: click_until_absent", (
                "    - method: dblclick\n"
                "    - method: click_until_absent"
            )),
        ):
            ok, _, data = recipes.validate_recipe(text.replace(old, new, 1))
            self.assertFalse(ok)
            self.assertIsNone(data)

        base = yaml.safe_load(text)
        methods = base["services"][0]["steps"][1]["methods"]
        invalid_method_lists = (
            [copy.deepcopy(methods[1])],
            [copy.deepcopy(methods[0]), copy.deepcopy(methods[1]),
             {"method": "first"}],
            [copy.deepcopy(methods[0]), copy.deepcopy(methods[1]),
             copy.deepcopy(methods[1])],
        )
        for invalid_methods in invalid_method_lists:
            invalid = copy.deepcopy(base)
            invalid["services"][0]["steps"][1]["methods"] = invalid_methods
            ok, _, data = recipes.validate_recipe(yaml.safe_dump(invalid))
            self.assertFalse(ok)
            self.assertIsNone(data)

        nested = copy.deepcopy(base)
        nested["services"][0]["steps"] = [{
            "step": 1,
            "methods": [{"method": "expect_download"}],
            "steps": [{
                "step": 1,
                "methods": copy.deepcopy(methods),
            }],
        }]
        ok, _, data = recipes.validate_recipe(yaml.safe_dump(nested))
        self.assertFalse(ok)
        self.assertIsNone(data)

        recursive = copy.deepcopy(base)
        recursive["services"][0]["steps"] = [{
            "step": 1,
            "methods": [{"method": "expect_download"}],
            "steps": [{
                "step": 2,
                "methods": [{"method": "expect_download"}],
                "steps": [{
                    "step": 3,
                    "methods": [{"method": "click", "arguments": [{"selector": "#invoice"}]}],
                }],
            }],
        }]
        ok, error, data = recipes.validate_recipe(yaml.safe_dump(recursive))
        self.assertTrue(ok, error)
        self.assertIsNotNone(data)

    def test_runner_dispatches_terminal_action_on_resolved_locator(self):
        locator = object()

        class Page:
            def evaluate(self, script):
                return True if "MutationObserver" in script else []

            def locator(self, **_kwargs):
                return locator

        bcs = SimpleNamespace(page=Page(), service="sample")
        action = mock.Mock()
        step = {"step": 1, "methods": [
            {"method": "locator", "arguments": [{"selector": ".invoice"}]},
            {"method": "download_all", "arguments": [{
                "key_attribute": "href",
                "max_items": 2,
                "timeout_ms": 10,
                "event_window_ms": 2,
            }]},
        ]}

        state = runner._process_step(
            bcs, step, collection_actions={"download_all": action}
        )

        self.assertFalse(state.error_status)
        action.assert_called_once_with(locator, {
            "key_attribute": "href", "max_items": 2, "timeout_ms": 10,
            "event_window_ms": 2,
        })
        self.assertIn("download_all", state.locator_action)

    def test_legacy_batch_dispatches_the_same_terminal_action(self):
        locator = object()

        class Page:
            def evaluate(self, script):
                return True if "MutationObserver" in script else []

            def locator(self, **_kwargs):
                return locator

        bcs = SimpleNamespace(page=Page(), service="sample")
        action = mock.Mock()
        step = {"step": 1, "methods": [
            {"method": "locator", "arguments": [{"selector": ".invoice"}]},
            {"method": "download_all", "arguments": [{
                "key_attribute": "href",
                "max_items": 2,
                "timeout_ms": 10,
                "event_window_ms": 2,
            }]},
        ]}

        state = batch_runner.process_step(
            bcs, step, collection_actions={"download_all": action}
        )

        self.assertFalse(state.error_status)
        action.assert_called_once_with(locator, {
            "key_attribute": "href", "max_items": 2, "timeout_ms": 10,
            "event_window_ms": 2,
        })

    def test_legacy_batch_records_partial_collection_as_failure(self):
        finalized = []

        class FakeDB:
            def __init__(self, _path):
                pass

            def create_service_run_table(self, _service):
                return "PageStatus_sample_Run1"

            def insert_page_status(self, _table, _state):
                pass

            def finalize_service_run(self, **kwargs):
                finalized.append(kwargs)

            def close_connection(self):
                pass

        class FakePage:
            context = SimpleNamespace(clear_cookies=lambda: None)

            def close(self):
                pass

        class FakeContext:
            def new_page(self):
                return FakePage()

            def close(self):
                pass

        bcs = SimpleNamespace(
            yml={"services": [{
                "serviceName": "sample",
                "steps": [{
                    "step": 1,
                    "methods": [
                        {"method": "locator"},
                        {"method": "download_all", "arguments": [{
                            "key_attribute": "href",
                            "max_items": 2,
                            "timeout_ms": 10,
                            "event_window_ms": 2,
                        }]},
                    ],
                }],
            }]},
            usr="alice",
        )

        def partial_step(_bcs, _step, collection_actions=None):
            collection_actions["download_all"](object(), {})

        def partial_download(_page, _context, _locator, save, _options):
            save(SimpleNamespace(
                suggested_filename="one.pdf",
                url="https://example.test/one.pdf",
                save_as=lambda _path: None,
            ))
            raise CollectionError("second item failed")

        class FakePlaywright:
            def __enter__(self):
                return SimpleNamespace()

            def __exit__(self, *_args):
                pass

        with mock.patch.object(
            batch_runner, "sync_playwright", return_value=FakePlaywright()
        ), mock.patch.object(
            batch_runner, "InitBrowser", return_value=FakeContext()
        ), mock.patch.object(
            batch_runner, "DatabaseManager", FakeDB
        ), mock.patch.object(
            batch_runner, "process_step", side_effect=partial_step
        ), mock.patch.object(
            batch_runner.collection, "download_all",
            side_effect=partial_download,
        ):
            files, aborted = batch_runner.perform_actions(bcs)

        self.assertTrue(aborted)
        self.assertEqual(files, [])
        self.assertEqual(finalized[0]["result"], "failure")
        self.assertIn("one.pdf", finalized[0]["download_info"])

    def test_collection_step_does_not_use_generic_automatic_retry(self):
        ctx = SimpleNamespace(bcs=object(), debug=False)
        step = {"step": 1, "methods": [
            {"method": "locator", "arguments": [{"selector": ".invoice"}]},
            {"method": "download_all", "arguments": [{
                "key_attribute": "href",
                "max_items": 2,
                "timeout_ms": 10,
                "event_window_ms": 2,
            }]},
        ]}
        with mock.patch.object(
            runner, "_process_step", side_effect=runner.StepAbortError("stop")
        ) as process:
            with self.assertRaisesRegex(runner.StepAbortError, "stop"):
                runner._execute_step(ctx, step)
        self.assertEqual(process.call_count, 1)

    def test_daemon_adapter_keeps_partial_result_and_rejects_run_name_collision(self):
        first = SimpleNamespace(suggested_filename="invoice.pdf")
        second = SimpleNamespace(suggested_filename="invoice.pdf")
        ctx = SimpleNamespace(
            page=object(),
            context=object(),
            collection_filenames=set(),
            files_downloaded=[],
            run_id=7,
            task={"id": 3},
            db=object(),
        )

        calls = 0

        completed_sets = []

        def exercise(_page, _context, _locator, save, _options,
                     *, completed_keys):
            nonlocal calls
            calls += 1
            completed_sets.append(completed_keys)
            save(first if calls == 1 else second)

        with mock.patch.object(
            runner.downloads, "track_download", return_value={
                "url": "https://example.test/invoice",
                "filename": "invoice.pdf",
            }
        ) as track, mock.patch.object(
            runner.collection, "download_all", side_effect=exercise
        ):
            actions = runner._collection_actions(ctx)
            options = {
                "key_attribute": "href", "max_items": 2,
                "timeout_ms": 10, "event_window_ms": 2,
            }
            actions["download_all"](object(), options)
            with self.assertRaisesRegex(CollectionError, "duplicate"):
                runner._collection_actions(ctx)["download_all"](
                    object(), options
                )

        self.assertEqual(track.call_count, 1)
        self.assertIs(completed_sets[0], completed_sets[1])
        self.assertEqual(ctx.files_downloaded, [{
            "url": "https://example.test/invoice",
            "suggested_filename": "invoice.pdf",
            "result": "success",
        }])

    def test_collection_action_rejects_an_earlier_side_effect(self):
        click = mock.Mock()
        page = SimpleNamespace(
            evaluate=lambda script: True if "MutationObserver" in script else [],
            locator=lambda **_kwargs: SimpleNamespace(click=click),
        )
        bcs = SimpleNamespace(page=page, service="sample")
        step = {"step": 1, "methods": [
            {"method": "locator", "arguments": [{"selector": ".invoice"}]},
            {"method": "click"},
            {"method": "download_all", "arguments": [{
                "key_attribute": "href", "max_items": 2,
                "timeout_ms": 10, "event_window_ms": 2,
            }]},
        ]}

        with self.assertRaisesRegex(
            runner.StepAbortError, "exactly one locator method"
        ):
            runner._process_step(
                bcs, step, collection_actions={"download_all": mock.Mock()}
            )
        click.assert_not_called()

        step["methods"][1] = {"method": "dblclick"}
        with self.assertRaisesRegex(
            runner.StepAbortError, "exactly one locator method"
        ):
            runner._process_step(
                bcs, step, collection_actions={"download_all": mock.Mock()}
            )


@unittest.skipUnless(
    os.environ.get("BILLCOLLECTOR_BROWSER_TESTS") == "1",
    "set BILLCOLLECTOR_BROWSER_TESTS=1 for loopback Chromium smoke",
)
class BrowserCollectionTests(unittest.TestCase):
    def test_paginate_then_download_from_loopback_portal(self):
        pdf = b"%PDF-1.4\n%%EOF\n"

        class Portal(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    body = b"""
                    <div id='rows'>
                      <button class='invoice' data-key='one'
                              onclick='downloadOne()'>One</button>
                    </div>
                    <button id='more' onclick='loadMore()'>More</button>
                    <script>
                    let page = 1;
                    function downloadOne() {
                      history.pushState({}, '', '/view');
                      const link = document.createElement('a');
                      link.href = '/one.pdf';
                      link.click();
                    }
                    function loadMore() {
                      page += 1;
                      const link = document.createElement('a');
                      link.className = 'invoice';
                      link.dataset.key = String(page);
                      link.href = '/' + page + '.pdf';
                      link.textContent = String(page);
                      if (page === 2) link.target = '_blank';
                      document.querySelector('#rows').appendChild(link);
                      if (page === 3) document.querySelector('#more').remove();
                    }
                    window.addEventListener('popstate', () => {
                      const rows = document.querySelector('#rows');
                      const content = rows.innerHTML;
                      rows.innerHTML = '';
                      setTimeout(() => { rows.innerHTML = content; }, 150);
                    });
                    </script>
                    """
                    mime = "text/html"
                elif self.path == "/multiple":
                    body = b"""
                    <button class='invoice' data-key='one' onclick='many()'>
                      Download
                    </button>
                    <script>
                    function download(path) {
                      const link = document.createElement('a');
                      link.href = path;
                      link.click();
                    }
                    function many() {
                      download('/one.pdf');
                      setTimeout(() => download('/2.pdf'), 700);
                    }
                    </script>
                    """
                    mime = "text/html"
                elif self.path in {"/one.pdf", "/2.pdf", "/3.pdf"}:
                    body = pdf + self.path.encode()
                    mime = "application/pdf"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                if mime == "application/pdf":
                    name = self.path.strip("/")
                    self.send_header(
                        "Content-Disposition", f"attachment; filename={name}"
                    )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        from playwright.sync_api import sync_playwright

        if _REQUESTED_BROWSER_PATH:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _REQUESTED_BROWSER_PATH
        with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            result = click_until_absent(page, page.locator("#more"), {
                "progress_selector": ".invoice",
                "max_clicks": 2,
                "timeout_ms": 1000,
            })
            saved = []

            def save(download):
                path = Path(directory) / download.suggested_filename
                download.save_as(path)
                saved.append(path.name)
                return path.name

            records = download_all(
                page, context, page.locator(".invoice"), save, {
                    "key_attribute": "data-key",
                    "max_items": 3,
                    "timeout_ms": 10000,
                    "event_window_ms": 1000,
                }
            )

            self.assertEqual(result.clicks, 2)
            self.assertEqual(records, ["one.pdf", "2.pdf", "3.pdf"])
            self.assertEqual(saved, records)
            self.assertEqual(
                page.url, f"http://127.0.0.1:{server.server_port}/"
            )

            page.goto(
                f"http://127.0.0.1:{server.server_port}/multiple"
            )
            with self.assertRaisesRegex(CollectionError, "produced 2 files"):
                download_all(
                    page, context, page.locator(".invoice"), save, {
                        "key_attribute": "data-key",
                        "max_items": 1,
                        "timeout_ms": 3000,
                        "event_window_ms": 1000,
                    }
                )
            self.assertEqual(saved, records)
            browser.close()


if __name__ == "__main__":
    unittest.main()
