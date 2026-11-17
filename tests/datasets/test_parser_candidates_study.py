"""Synthetic-only study tests; direct unittest entry avoids GPU pytest hooks."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from parser_study_support import enable_geometry_only_imports, within  # noqa: E402

enable_geometry_only_imports()
from audit_parser_candidates import candidate_metrics, output_roots  # noqa: E402

from layoutpatch.datasets.parser_candidates import (  # noqa: E402
    FRAME,
    LEGACY,
    NEW,
    POINTS,
    CandidatePageError,
    augment_page,
    map_box,
    transform_spec,
    validate_box,
)
from layoutpatch.evaluation.localization import question_macro, unit_metrics  # noqa: E402


def fixture():
    box = [.1, .2, .8, .6]
    payload = {"schema": "docvortex.middle", "schema_version": "2.0",
               "extensions": {"docvortex_layout": {"version": 1, "pages": [{"page_idx": 0, "width_pt": 100, "height_pt": 200}]}},
               "pages": [{"page_idx": 0, "blocks": [{"index": 7, "type": "table", "bbox": box,
                                                      "content": [{"index": 0, "type": "table_body", "bbox": box, "content": "<table/>"},
                                                                  {"index": 1, "type": "table_caption", "bbox": [.1, .65, .8, .7], "content": [{"type": "text", "content": "Caption"}]}]}]}]}
    receipt = {"page_id": "doc_p0", "doc_id": "doc", "page_number": 1, "pdf_page_index": 0,
               "raw_sha256": "raw-sha", "coordinate_contract": LEGACY,
               "render": {"page_size": [200, 400], "pdf_size_points": [100, 200], "rotation": 0,
                          "cropbox": [0, 0, 100, 200], "mediabox": [0, 0, 100, 200]}}
    old = [{"page_id": "doc_p0", "doc_id": "doc", "page_number": 1, "pdf_page_index": 0, "layout_id": 7,
            "candidate_id": "doc_p0:block:7", "type": "table", "parser_type": "table", "parser_bbox_unit": box,
            "bbox": [20, 80, 160, 240], "page_size": [200, 400], "text": "original whole parent text", "text_source": "unknown"}]
    return payload, receipt, old


class ParserCandidateTests(unittest.TestCase):
    def test_parent_is_exact_and_child_outside_parent_is_allowed(self):
        raw, receipt, old = fixture()
        before = copy.deepcopy((raw, receipt, old))
        legacy, new, aliases, audit = augment_page(raw, receipt, old)
        self.assertEqual((raw, receipt, old), before)
        for key in ("layout_id", "bbox", "type", "text", "page_size"):
            self.assertEqual(new[0][key], old[0][key])
            self.assertEqual(legacy[0][key], old[0][key])
        self.assertEqual(new[1]["layout_id"], 8)
        self.assertEqual(new[1]["bbox"], [20, 260, 160, 280])
        self.assertEqual(new[1]["text"], "Caption")
        self.assertEqual(new[1]["type"], "text")
        self.assertEqual(aliases[0]["reason"], "parent_equal_body")
        self.assertEqual(audit["raw_bbox_count"], 3)
        self.assertNotEqual(new[0]["candidate_id"], legacy[0]["candidate_id"])

    def test_duplicate_caption_alias_preserves_text_and_source(self):
        raw, receipt, old = fixture()
        duplicate = copy.deepcopy(raw["pages"][0]["blocks"][0]["content"][1])
        duplicate["content"] = [{"type": "text", "content": "Second wording"}]
        raw["pages"][0]["blocks"][0]["content"].append(duplicate)
        _, new, aliases, audit = augment_page(raw, receipt, old)
        self.assertEqual(len(new), 2)
        self.assertEqual(aliases[-1]["text"], "Second wording")
        self.assertEqual(aliases[-1]["alias_of"], new[1]["candidate_id"])
        self.assertEqual(audit["raw_bbox_count"], len(new) + len(aliases))

    def test_near_duplicate_is_not_iou_deduplicated(self):
        raw, receipt, old = fixture()
        child = copy.deepcopy(raw["pages"][0]["blocks"][0]["content"][1])
        child["bbox"][0] += 1e-9
        raw["pages"][0]["blocks"][0]["content"].append(child)
        self.assertEqual(len(augment_page(raw, receipt, old)[1]), 3)

    def test_no_partial_new_page_on_invalid_child(self):
        raw, receipt, old = fixture()
        raw["pages"][0]["blocks"][0]["content"].append({"type": "table_caption", "bbox": [0, .8, 1.1, .9]})
        with self.assertRaises(CandidatePageError):
            augment_page(raw, receipt, old)
        self.assertEqual(len(old), 1)

    def test_nonmatching_body_rejected(self):
        raw, receipt, old = fixture()
        raw["pages"][0]["blocks"][0]["content"][0]["bbox"] = [.1, .2, .7, .6]
        with self.assertRaisesRegex(CandidatePageError, "body does not equal"):
            augment_page(raw, receipt, old)

    def test_unknown_deeper_geometry_not_silently_lost(self):
        raw, receipt, old = fixture()
        raw["pages"][0]["blocks"][0]["content"][1]["content"][0]["bbox"] = [.1, .65, .3, .7]
        with self.assertRaisesRegex(CandidatePageError, "unhandled nested"):
            augment_page(raw, receipt, old)

    def test_invalid_numeric_and_empty_boxes(self):
        for box in ([0, 0, 0, 1], [True, 0, 1, 1], [0, 0, float('nan'), 1], [-.1, 0, 1, 1], [1, 0, 0, 1]):
            with self.subTest(box=box), self.assertRaises(CandidatePageError):
                validate_box(box, [1, 1])

    def test_legacy_uses_raster_dimensions_not_pdf_times_two(self):
        raw, receipt, _ = fixture()
        raw["extensions"]["docvortex_layout"]["pages"][0]["width_pt"] = 595.276
        receipt["render"].update(page_size=[1191, 400], pdf_size_points=[595.276, 200], cropbox=[0, 0, 595.276, 200], mediabox=[0, 0, 595.276, 200])
        result = map_box([.2, .1, .8, .9], transform_spec(raw, receipt))
        self.assertEqual(result, [238.20000000000002, 40, 952.8000000000001, 360])

    def test_unrotated_pdf_frame_rotation_to_pixels(self):
        raw, receipt, _ = fixture()
        receipt["coordinate_contract"] = POINTS
        receipt["render"].update(page_size=[400, 200], rotation=90, pdf_to_render_matrix=[0, 1, -1, 0, 200, 0], render_scale=2)
        self.assertEqual(map_box([.1, .2, .3, .4], transform_spec(raw, receipt)), [240, 20, 320, 60])

    def test_rotated_parser_frame_not_rotated_twice(self):
        raw, receipt, _ = fixture()
        raw["extensions"]["docvortex_layout"]["pages"][0].update(width_pt=200, height_pt=100)
        receipt["coordinate_contract"] = FRAME
        receipt["render"].update(page_size=[400, 200], rotation=90, page_rect=[0, 0, 200, 100], pdf_to_render_matrix=[0, 1, -1, 0, 200, 0], render_scale=2)
        self.assertEqual(map_box([.1, .2, .3, .4], transform_spec(raw, receipt)), [40, 40, 120, 80])

    def test_wrong_candidate_identity_or_geometry_rejected(self):
        for field, value in (("layout_id", 9), ("bbox", [20, 80, 159, 240]), ("page_id", "other")):
            raw, receipt, old = fixture()
            old[0][field] = value
            with self.subTest(field=field), self.assertRaises(CandidatePageError):
                augment_page(raw, receipt, old)

    def test_empty_candidate_units_remain_in_question_macro(self):
        score, best = candidate_metrics([], [[0, 0, 1, 1]])
        self.assertEqual(best, [0.0])
        self.assertTrue(all(value == 0 for value in score.values()))
        values = question_macro([{"query_id": "q", **score}, {"query_id": "q", "oracle@0.5": 1}], "oracle@0.5")
        self.assertEqual(values, {"q": .5})

    def test_multi_gold_independent_vs_existing_one_to_one(self):
        pred = [{"layout_id": 3, "bbox": [0, 0, 20, 10]}]
        gold = [[0, 0, 10, 10], [10, 0, 20, 10]]
        values, _ = candidate_metrics(pred, gold)
        self.assertEqual(values["independent_gold_reach@0.5"], 1)
        self.assertEqual(values["greedy_all_candidates_gold_recall@0.5"], .5)
        self.assertEqual(values["greedy_all_candidates_gold_recall@0.5"], unit_metrics([pred[0]["bbox"]], gold, [20, 10])["gold_recall@5@0.5"])

    def test_parent_identity_namespace_and_repeatability(self):
        raw, receipt, old = fixture()
        a = augment_page(raw, receipt, old)
        b = augment_page(raw, receipt, old)
        self.assertEqual(a, b)
        self.assertTrue(all(r["candidate_id"].startswith(NEW + ":") for r in a[1]))

    def test_path_traversal_and_source_write_roots_rejected(self):
        with self.assertRaises(ValueError):
            within(Path.cwd(), "../outside")
        with self.assertRaises(ValueError):
            output_roots({"paths": {}}, "../bad")
        with self.assertRaises(ValueError):
            output_roots({"paths": {"artifacts_root": "data", "runs_root": "runs/parser_candidate_comparison/v1"}}, "valid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
