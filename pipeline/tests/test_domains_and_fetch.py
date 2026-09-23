import unittest

import httpx

from src import config, domains
from src.fetch import Fetcher, is_public_http_url

ARTICLE = "https://techcrunch.com/2026/09/22/acme-raises"


def html(*hrefs: str) -> str:
    return "<article>" + "".join(f'<a href="{h}">link</a>' for h in hrefs) + "</article>"


class DomainPickingTests(unittest.TestCase):
    def test_prefers_a_linked_site_matching_the_name(self):
        page = html("https://sequoiacap.com", "https://www.acmelabs.io/about", "https://twitter.com/acme")
        self.assertEqual(
            domains.pick_domain("Acme Labs", page, "", ARTICLE, None, ["Sequoia Cap"]),
            ("acmelabs.io", "article_link_name_match"),
        )

    def test_never_picks_publisher_social_or_investor_links(self):
        page = html("https://techcrunch.com/other", "https://linkedin.com/acme", "https://a16z.com", "https://acme.com")
        self.assertEqual(domains.candidate_links(page, ARTICLE, ["a16z"]), ["acme.com"])

    def test_model_domain_must_appear_in_the_article(self):
        self.assertEqual(
            domains.pick_domain("Zero", "<p>Visit zero.dev</p>", "Visit zero.dev", ARTICLE, "zero.dev", []),
            ("zero.dev", "model_domain_in_article"),
        )
        # A guessed domain that the article never mentions is refused.
        self.assertEqual(domains.pick_domain("Zero", "<p>nothing</p>", "nothing", ARTICLE, "zero.com", []), (None, "none"))

    def test_short_names_only_verify_in_title_or_site_name(self):
        self.assertFalse(domains._name_in("Aqua", "Pool supplies", "", "we love aqua colors"))
        self.assertTrue(domains._name_in("Aqua", "Aqua | Home", "", ""))
        self.assertTrue(domains._name_in("Rainmaker Technology Corporation", "Welcome", "", "rainmaker builds tools"))


class FetchSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_url_guard(self):
        for url in ["https://acme.com", "http://acme.io/path", "https://8.8.8.8"]:
            self.assertTrue(is_public_http_url(httpx.URL(url)), url)
        for url in ["http://169.254.169.254/latest/meta-data", "http://127.0.0.1:8080", "http://10.0.0.5",
                    "http://192.168.1.1", "http://[::1]/", "http://localhost/", "http://metadata.google.internal/",
                    "file:///etc/passwd", "ftp://acme.com"]:
            self.assertFalse(is_public_http_url(httpx.URL(url)), url)

    async def fetch(self, handler, url="https://acme.com/"):
        fetcher = Fetcher(transport=httpx.MockTransport(handler))
        try:
            return await fetcher.get(url)
        finally:
            await fetcher.close()

    async def test_redirects_to_internal_addresses_are_blocked(self):
        requested = []

        def handler(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

        self.assertIsNone(await self.fetch(handler))
        self.assertEqual(requested, ["https://acme.com/"])

    async def test_internal_addresses_are_never_requested(self):
        requested = []
        self.assertIsNone(await self.fetch(lambda r: requested.append(r) or httpx.Response(200), "http://127.0.0.1/"))
        self.assertEqual(requested, [])

    async def test_oversized_bodies_are_dropped(self):
        big = b"x" * (config.MAX_RESPONSE_BYTES + 1)
        self.assertIsNone(await self.fetch(lambda r: httpx.Response(200, content=big)))
        # Streamed without a content-length header, still capped.
        chunks = httpx.ByteStream(big)
        self.assertIsNone(await self.fetch(lambda r: httpx.Response(200, stream=chunks)))

    async def test_normal_pages_are_returned(self):
        resp = await self.fetch(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>hi</p>"))
        self.assertEqual(resp.text, "<p>hi</p>")
        self.assertIsNone(await self.fetch(lambda r: httpx.Response(404)))


if __name__ == "__main__":
    unittest.main()
