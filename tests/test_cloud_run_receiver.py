import unittest

from src.cloud_run_receiver import _parse_request_body


class CloudRunReceiverTest(unittest.TestCase):
    def test_parse_request_body_accepts_json(self) -> None:
        payload = _parse_request_body('{"secret":"change-me","entry":78000}')

        self.assertEqual(payload["secret"], "change-me")
        self.assertEqual(payload["entry"], 78000)

    def test_parse_request_body_repairs_bare_keys(self) -> None:
        payload = _parse_request_body('{secret:"change-me",entry:78000}')

        self.assertEqual(payload["secret"], "change-me")
        self.assertEqual(payload["entry"], 78000)

    def test_parse_request_body_accepts_smart_quotes(self) -> None:
        payload = _parse_request_body('{“secret”:“change-me”,“entry”:78000}')

        self.assertEqual(payload["secret"], "change-me")
        self.assertEqual(payload["entry"], 78000)


if __name__ == "__main__":
    unittest.main()
