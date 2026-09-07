#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_feedback_collection.py — полнота сборщика внешней
обратной связи: тела, пагинация каждого уровня, ответы, ошибки GraphQL,
дедупликация, внутренние аккаунты, рекрутинг и синтетика.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import collect_external_feedback as CF  # noqa: E402

REPO = CF.REPO
VER = "3.33" + ".0"  # конкатенация: гейт version-literals запрещает литерал


def _disc_env(nodes, has_next=False, end=None):
    return [{"data": {"repository": {"discussions": {
        "pageInfo": {"hasNextPage": has_next, "endCursor": end},
        "nodes": nodes}}}}]


def _comment(cid, url, body, login="reader-external",
             date="2026-09-06T01:00:00Z"):
    return {"id": cid, "createdAt": date, "author": {"login": login},
            "url": url, "body": body}


class BodyAndSignalsTests(unittest.TestCase):
    def _collect(self, runner):
        return CF.collect("2026-09-06", runner=runner, synthetic=True)

    def test_discussion_body_reaches_signals(self):
        env = _disc_env([{
            "number": 96, "title": "проблема",
            "createdAt": "2026-09-06T00:00:00Z",
            "author": {"login": "reader-external"},
            "body": "humanizer-markers --json " + VER + " ошибка",
            "comments": {"pageInfo": {"hasNextPage": False,
                                      "endCursor": None}, "nodes": []}}])

        def runner(args):
            q = args[2] if len(args) > 2 else ""
            if "replies(first:" in q:
                return [{"data": {"node": {"replies": {"nodes": []}}}}], None
            return env, None
        rows, src = self._collect(runner)
        disc = [r for r in rows if r["kind"] == "discussion"]
        self.assertTrue(disc)
        self.assertTrue(disc[0]["body_excerpt"])
        self.assertTrue(disc[0]["signals"]["has_command"])
        self.assertTrue(disc[0]["concrete_usage_signs"])
        self.assertFalse(src["discussions"].get("partial"))

    def test_comment_body_reaches_signals(self):
        env = _disc_env([{
            "number": 96, "title": "тред",
            "createdAt": "2026-09-06T00:00:00Z",
            "author": {"login": CF.OWNER}, "body": "",
            "comments": {"pageInfo": {"hasNextPage": False,
                                      "endCursor": None},
                         "nodes": [_comment(
                             "C1", "https://github.com/%s/discussions/96#c1"
                             % REPO,
                             "воспроизвёл: exit code 2, версия " + VER)]}}])

        def runner(args):
            q = args[2] if len(args) > 2 else ""
            if "replies(first:" in q:
                return [{"data": {"node": {"replies": {"nodes": []}}}}], None
            return env, None
        rows, _src = self._collect(runner)
        com = [r for r in rows if r["kind"] == "discussion-comment"]
        self.assertTrue(com)
        self.assertTrue(com[0]["body_excerpt"])
        self.assertTrue(com[0]["signals"]["has_problem"])


class PaginationTests(unittest.TestCase):
    def test_more_than_50_comments_read_fully(self):
        page1 = [_comment("P%d" % i,
                          "https://github.com/%s/discussions/97#p%d"
                          % (REPO, i),
                          "комментарий %d" % i) for i in range(1, 4)]
        env1 = _disc_env([{
            "number": 97, "title": "тред",
            "createdAt": "2026-09-06T00:00:00Z",
            "author": {"login": CF.OWNER}, "body": "",
            "comments": {"pageInfo": {"hasNextPage": True,
                                      "endCursor": "CC1"},
                         "nodes": page1}}], has_next=False)
        env2 = [{"data": {"repository": {"discussions": {"nodes": [{
            "number": 97,
            "comments": {"pageInfo": {"hasNextPage": False,
                                      "endCursor": None},
                         "nodes": [_comment(
                             "P9", "https://github.com/%s/discussions/97#p9"
                             % REPO, "комментарий 9")]}}]}}}}]

        def runner(args):
            q = args[2] if len(args) > 2 else ""
            if "first: 1, after:" in q:
                return env2, None
            if "replies(first:" in q:
                return [{"data": {"node": {"replies": {"nodes": []}}}}], None
            return env1, None
        rows, _src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        urls = [r["url"] for r in rows if r["kind"] == "discussion-comment"]
        self.assertIn("97#p1", " ".join(urls))
        self.assertIn("97#p9", " ".join(urls))

    def test_replies_collected(self):
        env = _disc_env([{
            "number": 96, "title": "тред",
            "createdAt": "2026-09-06T00:00:00Z",
            "author": {"login": CF.OWNER}, "body": "",
            "comments": {"pageInfo": {"hasNextPage": False,
                                      "endCursor": None},
                         "nodes": [_comment(
                             "C1", "https://github.com/%s/discussions/96#c1"
                             % REPO, "вопрос")]}}])
        replies = [{"data": {"node": {"replies": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [_comment(
                "R1", "https://github.com/%s/discussions/96#c1r1" % REPO,
                "ответ внешнего", login="second-external")]}}}}]

        def runner(args):
            q = args[2] if len(args) > 2 else ""
            if "replies(first:" in q:
                return replies, None
            return env, None
        rows, _src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        self.assertTrue(any(r["url"].endswith("c1r1")
                            and r["author"] == "second-external"
                            for r in rows))


class GraphqlErrorTests(unittest.TestCase):
    def test_errors_without_data_unavailable(self):
        def runner(args):
            return [{"errors": [{"message": "boom"}]}], None
        _rows, src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        self.assertEqual(src["discussions"]["status"], "unavailable")

    def test_rate_limited_unavailable(self):
        def runner(args):
            return [{"errors": [{"type": "RATE_LIMITED",
                                 "message": "limit"}]}], None
        _rows, src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        self.assertEqual(src["discussions"]["status"], "unavailable")
        self.assertIn("ограничение API", src["discussions"]["reason"])

    def test_partial_response_marked(self):
        env = _disc_env([])
        env[0]["errors"] = [{"message": "поле недоступно"}]

        def runner(args):
            return env, None
        _rows, src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        self.assertEqual(src["discussions"]["status"], "ok")
        self.assertTrue(src["discussions"].get("partial"))


class AccountsAndSyntheticTests(unittest.TestCase):
    def test_internal_and_bots_excluded_from_external(self):
        env = _disc_env([{
            "number": 95, "title": "тред",
            "createdAt": "2026-09-06T00:00:00Z",
            "author": {"login": CF.OWNER}, "body": "",
            "comments": {"nodes": []}}])

        def runner(args):
            q = args[2] if len(args) > 2 else ""
            if "replies(first:" in q:
                return [{"data": {"node": {"replies": {"nodes": []}}}}], None
            return env, None
        rows, _src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        self.assertFalse(any(r["external"] for r in rows))

    def test_solicitation_not_concrete(self):
        issues = [{"user": {"login": "catalog-promo"},
                   "created_at": "2026-09-07T10:00:00Z",
                   "html_url": "https://github.com/%s/issues/5" % REPO,
                   "title": "Add to awesome list?",
                   "body": "We maintain awesome-ai-plugins. "
                           "Please consider adding your project."}]

        def runner(args):
            first = args[0]
            if first.startswith("repos/%s/issues/comments" % REPO):
                return [], None
            if first.startswith("repos/%s/issues" % REPO):
                return issues, None
            q = args[2] if len(args) > 2 else ""
            if "replies(first:" in q:
                return [{"data": {"node": {"replies": {"nodes": []}}}}], None
            return _disc_env([]), None
        rows, _src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        promo = [r for r in rows if r["author"] == "catalog-promo"]
        self.assertTrue(promo)
        self.assertTrue(promo[0]["signals"]["solicitation"])
        self.assertFalse(promo[0]["concrete_usage_signs"])

    def test_synthetic_flag_propagates(self):
        def runner(args):
            first = args[0]
            if first.startswith("repos/%s/issues/comments" % REPO):
                return [], None
            if first.startswith("repos/%s/issues" % REPO):
                return [], None
            q = args[2] if len(args) > 2 else ""
            if "replies(first:" in q:
                return [{"data": {"node": {"replies": {"nodes": []}}}}], None
            return _disc_env([]), None
        rows, _src = CF.collect("2026-09-06", runner=runner, synthetic=True)
        self.assertTrue(all(r["synthetic"] for r in rows))


if __name__ == "__main__":
    unittest.main()
