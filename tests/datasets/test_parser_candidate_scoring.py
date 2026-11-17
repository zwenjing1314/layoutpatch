"""Synthetic safeguards for fixed candidate scoring; no external outcome tuning."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_parser_candidate_study as s
import torch


class ScoringContracts(unittest.TestCase):
    def test_wrong_page_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            s.validate_page({"page_id": "wrong", "embedding": torch.ones(1031, 128)}, "right")

    def test_query_identity_and_attention(self):
        q = torch.ones(12, 128)
        token = {"shape": [12, 128], "attention_mask": [1] * 12, "input_ids": [1, 2] + [0] * 10}
        payload = {"embeddings": {"q": q}, "tokens": {"q": token}}
        s.validate_queries(payload, {"ids": ["q"]}, {"q"}, 0)
        with self.assertRaises(ValueError):
            s.validate_queries(payload, {"ids": ["other"]}, {"q"}, 0)
        token["attention_mask"][0] = 0
        with self.assertRaises(ValueError):
            s.validate_queries(payload, {"ids": ["q"]}, {"q"}, 0)

    def test_seed_selection_fixed(self):
        rows = [
            dict(seed=i, selected_epoch=e, selection_role="source_val")
            for i, e in enumerate([1, 1, 5])
        ]
        s.validate_seeds(rows)
        with self.assertRaises(ValueError):
            s.validate_seeds(rows[:2])
        rows[2]["selected_epoch"] = 1
        with self.assertRaises(ValueError):
            s.validate_seeds(rows)

    def test_cross_candidate_cache_rejected(self):
        page = dict(page_id="p", parser_image_sha256="image", page_cache_sha256="P")
        old = s.cache_identity("old", "a", page, "weight", "code")
        new = s.cache_identity("new", "b", page, "weight", "code")
        s.check_cache({"identity": old}, old)
        with self.assertRaises(ValueError):
            s.check_cache({"identity": old}, new)
        changed = {**old, "checkpoint_sha256": "other"}
        with self.assertRaises(ValueError):
            s.check_cache({"identity": old}, changed)

    def test_empty_keeps_unit_and_metrics(self):
        unit = dict(
            query_id="q",
            doc_id="d",
            page_id="p",
            unit_id="q:p",
            page_size=[100, 100],
            gold_boxes=[[0, 0, 50, 50]],
        )
        row = s.prediction(unit, [], [], torch.zeros(0, 1024), "old", "A")
        self.assertEqual(row["unit_id"], "q:p")
        self.assertTrue(all(row[m] == 0 for m in s.METRICS))

    def test_tie_and_numeric_sentinels(self):
        self.assertEqual(s.rank_candidates([1, 1], [9, 2]), [1, 0])
        s.validated_scores([-float("inf")], torch.zeros(1, 1024))
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                s.validated_scores([bad], torch.zeros(1, 1024))
        with self.assertRaises(ValueError):
            s.validated_scores([-float("inf")], torch.ones(1, 1024))

    def test_zero_text_preserves_geometry_and_matches_ablation(self):
        rows = [dict(layout_id=0, bbox=[0, 0, 224, 224], page_size=[448, 448], type="text")]
        zero = s.page_layout(rows, torch.zeros(1, 1024))
        self.assertEqual(int(zero["types"][0]), 1)
        self.assertTrue(bool(zero["mask"].all()))
        self.assertGreater(float(zero["cover_mass"].sum()), 0)
        active = zero["cover_mass"][:, 0] > 0
        self.assertTrue(
            torch.allclose(zero["W_attn"][active].sum(-1), torch.ones(int(active.sum())))
        )
        model = s.InputAblatedD("text").eval()
        patches = torch.randn(1024, 128)
        noisy = {**zero, "text": torch.randn(1, 1024)}
        with torch.inference_mode():
            self.assertTrue(torch.equal(model(patches, zero), model(patches, noisy)))
        state = model.state_dict()
        state.pop(next(iter(state)))
        with self.assertRaises(RuntimeError):
            model.load_state_dict(state, strict=True)

    def test_one_to_one_recall_not_independent(self):
        result = s.unit_metrics([[0, 0, 50, 50]], [[0, 0, 50, 50], [0, 0, 50, 50]], [100, 100])
        self.assertEqual(result["gold_recall@5@0.5"], 0.5)
        self.assertEqual(result["cov@5"], 1)


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main()
