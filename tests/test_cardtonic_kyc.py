import unittest
from bs4 import BeautifulSoup
from app.adapters.giftcard.cardtonic_kyc import parse_kyc_article


class CardtonicKycTests(unittest.TestCase):
    def test_requirements_notes_and_unknown_limits(self):
        soup = BeautifulSoup('''<h1>Verification guide</h1><time datetime="2026-07-08T13:59:26Z"></time>
        <article><h3>Basic KYC:</h3><ol><li><p>Provide identity details.</p></li>
        <li>Take a photo.</li><li>Tap verify.</li></ol><p>Verification is quick.</p>
        <h3>Advanced KYC:</h3><p>Upload identification and address evidence. Tap submit.</p>
        <p>Available in Nigeria only.</p><section><ul><li><a href="/en/articles/other">Related guide</a></li></ul></section></article>''', 'html.parser')
        document = parse_kyc_article(soup)
        self.assertEqual(len(document['levels']), 2)
        self.assertEqual(len(document['levels'][0]['requirements']), 2)
        self.assertEqual(document['levels'][1]['requirements'], ['Upload identification and address evidence.'])
        self.assertIn('Nigeria', document['levels'][1]['notes'])
        self.assertNotIn('Related guide', document['content'])
        self.assertIsNotNone(document['updated_at'].tzinfo)
        self.assertIsNone(document['levels'][0].get('fiat_withdrawal_limit'))

    def test_missing_sections_fail(self):
        with self.assertRaises(ValueError):
            parse_kyc_article(BeautifulSoup('<h1>Help</h1><article>Search instead</article>', 'html.parser'))


if __name__ == '__main__':
    unittest.main()
