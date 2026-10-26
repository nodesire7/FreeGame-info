import copy
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from render_html import build_share_payload, render_html, render_history_page, render_steam_card


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = str(ROOT / 'epic-freebies.html.template')


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def find(self, tag, **attrs):
        return [node for node_tag, node in self.nodes
                if node_tag == tag and all(node.get(k) == v for k, v in attrs.items())]


def snapshot():
    return {
        'fetchedAt': '2026-10-26T12:00:00+08:00',
        'epic': {'now': [{
            'title': 'A <B> & 中文游戏 ' + 'LongTitle' * 20,
            'description': '完整介绍 <script>不可执行</script>',
            'link': 'https://store.epicgames.com/example?x=1&y=2',
            'cover': '', 'publisher': '发行商 <A>', 'creator': '开发商 & B',
            'isFreeNow': True, 'freeEndAt': 1893456000000,
            'originalPriceDesc': '¥99.00',
        }], 'upcoming': []},
        'steam': [], 'psn': [], 'gog': [], 'xbox': [], 'itad': [],
    }


class RenderUIRegressionTests(unittest.TestCase):
    maxDiff = 300

    def test_steam_prefers_available_high_resolution_header_image(self):
        game = {'title': 'Example', 'link': 'https://example.com/game',
                'image': 'https://example.com/capsule_231x87.jpg',
                'headerImage': 'https://example.com/header.jpg'}
        images = Document(render_steam_card(game)).find('img')
        self.assertEqual(images[0]['src'], game['headerImage'])

    def test_all_platform_store_actions_use_the_shared_button_style(self):
        data = snapshot()
        game = {'title': 'Example', 'link': 'https://example.com/game',
                'url': 'https://example.com/game', 'description': '', 'price': '免费'}
        for key in ['steam', 'psn', 'gog', 'xbox']:
            data[key] = [game.copy()]
        data['itad'] = {'deals': [game.copy()], 'bundles': []}
        doc = Document(render_html(data, TEMPLATE))
        links = doc.find('a', href='https://example.com/game')
        self.assertEqual(len(links), 5)
        for link in links:
            self.assertIn('action', link.get('class', '').split())
        epic_link = doc.find('a', href=data['epic']['now'][0]['link'])[0]
        self.assertIn('action', epic_link.get('class', '').split())

    def test_existing_share_download_remains_enabled_without_payload(self):
        source = render_html({}, TEMPLATE, share_webp_url='history/records/existing.webp')
        share = Document(source).find('a', href='history/records/existing.webp')[0]
        self.assertNotEqual(share.get('aria-disabled'), 'true')

    def test_share_download_resolves_database_relative_image_path(self):
        for input_url, expected in [
            ('records/20261026120000白嫖信息.webp', 'history/records/20261026120000白嫖信息.webp'),
            ('history/records/already.webp', 'history/records/already.webp'),
            ('https://example.com/share.webp', 'https://example.com/share.webp'),
        ]:
            with self.subTest(input_url=input_url):
                doc = Document(render_html(snapshot(), TEMPLATE, share_webp_url=input_url))
                share = next(n for tag, n in doc.nodes if 'data-share-button' in n)
                self.assertEqual(share['href'], expected)

    def test_epic_metadata_are_separate_elements_without_literal_markup(self):
        doc = Document(render_html(snapshot(), TEMPLATE))
        text = ''.join(doc.text)
        self.assertNotIn('</span><span', text)
        self.assertIn('发行：发行商 <A>', text)
        self.assertIn('开发：开发商 & B', text)

    def test_history_embeds_same_styles_without_online_css_runtime(self):
        source = render_history_page([snapshot()], template_path=TEMPLATE)
        template = Path(TEMPLATE).read_text()
        style = template.split('<style>', 1)[1].split('</style>', 1)[0]
        self.assertIn(style, source)
        self.assertNotIn('cdn.tailwindcss.com', source)

    def test_home_styles_do_not_require_online_runtime(self):
        self.assertNotIn('cdn.tailwindcss.com', render_html(snapshot(), TEMPLATE))

    def test_tabs_have_linked_labels_and_single_tab_stop(self):
        doc = Document(render_html(snapshot(), TEMPLATE))
        tabs = doc.find('button', role='tab')
        panels = {p.get('id'): p for p in doc.find('div', role='tabpanel')}
        self.assertEqual(len(tabs), 6)
        self.assertEqual(sum(t.get('tabindex') == '0' for t in tabs), 1)
        for tab in tabs:
            self.assertTrue(tab.get('id'))
            self.assertEqual(panels[tab['aria-controls']]['aria-labelledby'], tab['id'])

    def test_empty_share_action_is_disabled_and_has_no_placeholders(self):
        source = render_html({}, TEMPLATE)
        doc = Document(source)
        share = next(n for t, n in doc.nodes if 'data-share-button' in n)
        self.assertEqual(share.get('aria-disabled'), 'true')
        self.assertEqual(share.get('tabindex'), '-1')
        self.assertNotIn('{{', source)

    def test_rendering_preserves_snapshot_share_payload_and_links(self):
        data = snapshot()
        before = copy.deepcopy(data)
        payload = build_share_payload(data)
        source = render_html(data, TEMPLATE,
                             latest_history_ts='20261026120000',
                             share_webp_url='history/records/archive.webp')
        render_history_page([data], template_path=TEMPLATE)
        self.assertEqual(data, before)
        self.assertEqual(build_share_payload(data), payload)
        doc = Document(source)
        self.assertTrue(doc.find('a', href=data['epic']['now'][0]['link']))
        self.assertTrue(doc.find('a', href='history/records/archive.webp'))
        self.assertIn(data['epic']['now'][0]['title'], ''.join(doc.text))
        self.assertFalse(doc.find('script', src='不可执行'))

    def test_existing_new_format_samples_still_render(self):
        data = snapshot()
        for key, file in [('epic', 'EPIC.json'), ('psn', 'PSN.json'), ('itad', 'ITAD.json')]:
            data[key] = json.loads((ROOT / file).read_text())
        source = render_html(data, TEMPLATE)
        history = render_history_page([data], template_path=TEMPLATE)
        self.assertNotIn('{{', source)
        self.assertIn('历史记录', history)
        self.assertGreater(len(Document(source).find('article')), 0)

    def test_empty_history_retains_return_navigation(self):
        source = render_history_page([], template_path=TEMPLATE)
        doc = Document(source)
        self.assertIn('暂无历史记录', ''.join(doc.text))
        self.assertTrue(doc.find('a', href='../'))


if __name__ == '__main__':
    unittest.main()
