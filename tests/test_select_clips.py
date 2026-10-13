import unittest
from models import Sentence
from select_clips import select_clips, SelectionError

SENTS = [Sentence(f"جمله {i}.", i * 10.0, i * 10.0 + 9) for i in range(20)]  # 0..199 s


class Fake:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.prompt = result, error, None

    def generate_json(self, prompt):
        self.prompt = prompt
        if self.error:
            raise self.error
        return self.result


def item(rank, start, end, reason="r"):
    return {"rank": rank, "start": start, "end": end, "reason": reason}


class SelectTests(unittest.TestCase):
    def test_prompt_contains_rules_and_transcript_and_sorted_by_rank(self):
        c = Fake([item(2, 100, 140), item(1, 10, 50)])
        out = select_clips(SENTS, "RULES-XYZ", c)
        self.assertIn("RULES-XYZ", c.prompt)
        self.assertIn("0:10 جمله 1.", c.prompt)
        self.assertEqual([x.rank for x in out], [1, 2])

    def test_invalid_items_dropped(self):
        c = Fake([item(1, 50, 40), item(2, 500, 540), item(3, 10, 20),
                  item(4, 10, 120), item(5, 10, 50)])
        out = select_clips(SENTS, "r", c)
        self.assertEqual([x.rank for x in out], [5])

    def test_truncated_to_twelve(self):
        c = Fake([item(i, 0, 40) for i in range(1, 16)])
        self.assertEqual(len(select_clips(SENTS, "r", c)), 12)

    def test_malformed_raises_selection_error(self):
        for bad in (Fake(error=ValueError("bad json")), Fake(result="oops"), Fake(result=[{"x": 1}])):
            with self.assertRaises(SelectionError):
                select_clips(SENTS, "r", bad)


if __name__ == "__main__":
    unittest.main()
