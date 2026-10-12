"""
Mail templates (decision 8.138 e): every mail is a Jinja2 template as HTML and
plain text, autoescaped, in the site's colour theme with no logo, no image and
no resource from outside; the admin page previews them and sends a test to the
signed-in admin.
"""

from __future__ import annotations

import re

import pytest

from services import email_service
from services.email_service import MAIL_KINDS, TEMPLATE_DIR, sample_mail

CONFIG = {'frontend_url': 'https://csc.example.org/',
          'from_email': 'csc@example.org', 'reply_to': 'support@example.org',
          'from_name': 'Catalog of Second Chances', 'dev_mode': False}
KINDS = [entry['kind'] for entry in MAIL_KINDS]
EVIL = '<script>alert(1)</script> & "co" \'x\''


def _luminance(colour: str) -> float:
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
           for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# THE FILES -------------------------------------------------------------------
def test_every_mail_is_a_pair_of_template_files():
    for kind in [*KINDS, 'generic']:
        assert (TEMPLATE_DIR / f'{kind}.html.j2').is_file(), kind
        assert (TEMPLATE_DIR / f'{kind}.txt.j2').is_file(), kind
    assert (TEMPLATE_DIR / 'base.html.j2').is_file()
    assert (TEMPLATE_DIR / 'base.txt.j2').is_file()


def test_the_five_mails_that_exist_are_listed():
    assert KINDS == ['verification', 'reset', 'invitation', 'member_added',
                     'dataset_created']


def test_templates_are_ascii_only():
    for path in TEMPLATE_DIR.iterdir():
        path.read_bytes().decode('ascii')


# RENDERING -------------------------------------------------------------------
@pytest.mark.parametrize('kind', KINDS)
def test_a_mail_renders_html_and_text_with_sample_data(kind):
    mail = sample_mail(CONFIG, kind, 'someone@example.org')
    assert mail.to == 'someone@example.org'
    assert mail.subject.startswith('[CSC] ')
    for body in (mail.html, mail.text):
        assert 'https://csc.example.org/imprint' in body
        assert 'https://csc.example.org/privacy' in body
        assert 'You received this email because' in body
        assert 'Catalog of Second Chances' in body
        assert 'Please do not reply' not in body
    assert mail.html.lstrip().startswith('<!DOCTYPE html>')
    assert mail.text.endswith('\n') and not mail.text.endswith('\n\n')
    # one button: the link is in the HTML twice (the button and the plain
    # link below it) and once in the text
    urls = re.findall(r'href="([^"]+)"', mail.html)
    action = [u for u in urls if '/imprint' not in u and '/privacy' not in u]
    assert len(action) == 2 and action[0] == action[1]
    assert mail.text.splitlines().count(action[0].replace('&amp;', '&')) == 1


def test_the_reply_to_rules_of_8_124_hold():
    verification = sample_mail(CONFIG, 'verification', 'a@example.org')
    reset = sample_mail(CONFIG, 'reset', 'a@example.org')
    assert verification.reply_to == 'support@example.org'
    assert reset.reply_to == 'support@example.org'
    for kind in ('verification', 'reset'):
        mail = sample_mail(CONFIG, kind, 'a@example.org')
        assert 'Replies to this email reach the support of the catalog.' in mail.text
    for kind in ('invitation', 'member_added', 'dataset_created'):
        mail = sample_mail(CONFIG, kind, 'a@example.org')
        assert email_service.SAMPLE_INVITER_ADDRESS in mail.reply_to
        assert (f'Replies to this email reach '
                f'{email_service.SAMPLE_INVITER}.') in mail.text
    # no support address: nothing is said about replies
    quiet = {**CONFIG, 'reply_to': ''}
    mail = sample_mail(quiet, 'verification', 'a@example.org')
    assert mail.reply_to is None and 'Replies to this email' not in mail.text


def test_the_subject_prefix_and_the_sample_people_are_invented():
    for kind in KINDS:
        mail = sample_mail(CONFIG, kind, 'a@example.org')
        assert mail.subject.startswith(email_service.SUBJECT_PREFIX)
        assert '@example.org' in (mail.reply_to or 'x@example.org')


# ESCAPING --------------------------------------------------------------------
def _evil_mails():
    return [
        email_service.verification_mail(CONFIG, 'a@x.org', EVIL, 'tok'),
        email_service.reset_mail(CONFIG, 'a@x.org', EVIL, 'tok'),
        email_service.invitation_mail(CONFIG, 'a@x.org', 'CODE', EVIL,
                                      'mod@x.org', EVIL, [EVIL],
                                      '2026-12-01T00:00:00Z'),
        email_service.member_added_mail(CONFIG, 'a@x.org', EVIL, EVIL,
                                        [EVIL], EVIL, 'mod@x.org'),
        email_service.dataset_created_mail(CONFIG, 'a@x.org', EVIL, 'slug',
                                           EVIL, 'mod@x.org'),
        email_service.render(CONFIG, to='a@x.org', subject='s', title=EVIL,
                             paragraphs=[EVIL], reason=EVIL,
                             button=(EVIL, 'https://x.org/?a="b"&c=<d>')),
    ]


def test_html_escapes_what_is_inserted():
    for mail in _evil_mails():
        assert '<script>' not in mail.html
        assert '&lt;script&gt;' in mail.html
        assert '&amp; &#34;co&#34;' in mail.html or '&amp; &quot;co&quot;' in mail.html
        assert 'a="b"' not in mail.html or 'a=&#34;b&#34;' in mail.html


def test_a_quote_in_a_link_is_escaped_in_the_attribute():
    odd = _evil_mails()[-1]
    assert 'a="b"' not in odd.html
    assert 'a=&#34;b&#34;&amp;c=&lt;d&gt;' in odd.html


def test_text_is_not_html_escaped():
    for mail in _evil_mails():
        assert '&amp;' not in mail.text and '&lt;' not in mail.text
        assert '&#34;' not in mail.text
    assert 'alert(1)' in _evil_mails()[0].text


def test_a_template_that_lacks_a_value_fails_loudly():
    with pytest.raises(Exception):
        email_service.render_mail('member_added', CONFIG, to='a@x.org',
                                  subject='s', title='t', reason='r')


# THE STYLE -------------------------------------------------------------------
@pytest.mark.parametrize('kind', KINDS)
def test_the_site_theme_and_nothing_from_outside(kind):
    html = sample_mail(CONFIG, kind, 'a@example.org').html
    for colour in ('#f2f2f2', '#ffffff', '#000000', '#d9d9d9', '#333333',
                   '#ef509c', '#0000ff'):
        assert colour in html, colour
    # the wordmark is text; no logo, no image, no outside resource
    assert 'Catalog of Second Chances' in html
    assert '<img' not in html.lower()
    for pattern in (r'src\s*=', r'url\(', r'@import', r'<link\b', r'<script',
                    r'background-image', r'<iframe'):
        assert not re.search(pattern, html, re.I), pattern
    # table layout, charset, viewport and the colour scheme the client may use
    assert '<table role="presentation"' in html
    assert 'charset="UTF-8"' in html and 'name="viewport"' in html
    assert 'name="color-scheme" content="light dark"' in html
    assert '@media (prefers-color-scheme: dark)' in html


def test_the_button_text_is_black_because_white_on_magenta_is_too_pale():
    assert contrast('#ffffff', '#ef509c') < 4.5          # fails for 16 px text
    assert contrast('#000000', '#ef509c') >= 4.5
    assert contrast('#0000ff', '#ffffff') >= 4.5          # links
    assert contrast('#333333', '#ffffff') >= 4.5           # muted text
    for kind in KINDS:
        html = sample_mail(CONFIG, kind, 'a@example.org').html
        button = re.search(r'<a href="[^"]+" style="([^"]+)">[^<]+</a>', html)
        assert button, kind
        style = button.group(1)
        assert 'background-color: #ef509c' in style and 'color: #000000' in style


def test_every_element_with_a_colour_has_its_ground_set_too():
    """A client that inverts colours keeps the contrast when text and ground
    are both explicit: the page, the card and the button set a background."""
    html = sample_mail(CONFIG, 'verification', 'a@example.org').html
    assert 'bgcolor="#f2f2f2"' in html and 'bgcolor="#ffffff"' in html
    assert 'bgcolor="#ef509c"' in html
    # the dark scheme moves ground and text together
    dark = html.split('@media (prefers-color-scheme: dark)')[1].split('</style>')[0]
    assert 'background-color: #0d1117' in dark and 'color: #e6edf3' in dark
    assert contrast('#e6edf3', '#151b23') >= 4.5
    assert contrast('#4080ff', '#151b23') >= 4.5


# THE PLAIN-TEXT FALLBACK -----------------------------------------------------
@pytest.mark.parametrize('kind', KINDS)
def test_the_plain_text_stands_on_its_own(kind):
    text = sample_mail(CONFIG, kind, 'a@example.org').text
    assert '<' not in text and '>' not in text
    assert text.startswith('CATALOG OF SECOND CHANCES\n')
    lines = text.splitlines()
    assert lines[2] and not lines[2].startswith(' ')
    assert max(len(line) for line in lines if 'http' not in line) < 200
    assert '\n--\nYou received this email because' in text
    # the link is on a line of its own, after its label
    link = re.search(r'^([A-Z][^\n]*):\n(https://[^\n]+)$', text, re.M)
    assert link, text


def test_the_message_has_both_parts():
    mail = sample_mail(CONFIG, 'invitation', 'a@example.org')
    message = email_service._message(
        {'from_email': 'csc@example.org', 'from_name': 'CSC'}, mail)
    kinds = [part.get_content_type() for part in message.iter_parts()]
    assert kinds == ['text/plain', 'text/html']
    assert message['Reply-To'] and message['Subject'].startswith('[CSC] ')


# THE ADMIN ROUTES ------------------------------------------------------------
@pytest.fixture
def sent(monkeypatch):
    box = {'mails': [], 'failure': None}

    def send_mail(config, mail):
        box['mails'].append(mail)
        return box['failure']

    monkeypatch.setattr(email_service, 'send_mail', send_mail)
    return box


def test_the_preview_lists_every_mail_for_an_admin_only(api, auth_headers):
    admin = auth_headers('admin')
    got = api.get('/admin/mail-templates', headers=admin)
    assert got.status_code == 200, got.text
    mails = got.json()['mails']
    assert [m['kind'] for m in mails] == KINDS
    for mail in mails:
        assert mail['subject'].startswith('[CSC] ')
        assert mail['html'].lstrip().startswith('<!DOCTYPE html>')
        assert mail['text'].startswith('CATALOG OF SECOND CHANCES')
        assert mail['label'] and mail['when']
    assert api.get('/admin/mail-templates').status_code == 401
    assert api.get('/admin/mail-templates',
                   headers=auth_headers('user')).status_code == 403


def test_a_test_mail_goes_to_the_admins_own_address(api, db, auth_headers,
                                                     sent):
    admin = auth_headers('admin', username='ada')
    db['users'].update_one({'username': 'ada'},
                           {'$set': {'email': 'ada.lovelace@example.org'}})
    got = api.post('/admin/mail-templates/invitation/test', headers=admin)
    assert got.status_code == 200, got.text
    assert got.json() == {'kind': 'invitation',
                          'to': 'ada.lovelace@example.org'}
    assert len(sent['mails']) == 1
    mail = sent['mails'][0]
    assert mail.to == 'ada.lovelace@example.org'
    assert mail.subject.startswith('[CSC] You are invited')


def test_a_test_mail_for_every_kind_and_for_nothing_else(api, auth_headers, sent):
    admin = auth_headers('admin')
    for kind in KINDS:
        assert api.post(f'/admin/mail-templates/{kind}/test',
                        headers=admin).status_code == 200
    assert len(sent['mails']) == len(KINDS)
    assert api.post('/admin/mail-templates/nothing/test',
                    headers=admin).status_code == 404
    assert len(sent['mails']) == len(KINDS)


def test_a_failed_send_shows_its_reason(api, auth_headers, sent):
    sent['failure'] = 'SMTPRecipientsRefused: refused'
    got = api.post('/admin/mail-templates/reset/test',
                   headers=auth_headers('admin'))
    assert got.status_code == 502
    assert 'SMTPRecipientsRefused: refused' in got.json()['detail']


def test_a_test_mail_needs_an_admin_and_an_address(api, db, auth_headers, sent):
    assert api.post('/admin/mail-templates/reset/test').status_code == 401
    assert api.post('/admin/mail-templates/reset/test',
                    headers=auth_headers('user')).status_code == 403
    admin = auth_headers('admin')
    db['users'].update_many({'role': 'admin'}, {'$set': {'email': None}})
    got = api.post('/admin/mail-templates/reset/test', headers=admin)
    assert got.status_code == 400
    assert sent['mails'] == []


def test_mail_that_is_not_set_up_says_so(api, auth_headers, sent, monkeypatch):
    monkeypatch.delenv('SMTP_HOST', raising=False)
    got = api.post('/admin/mail-templates/reset/test',
                   headers=auth_headers('admin'))
    assert got.status_code == 502 and 'SMTP_HOST' in got.json()['detail']
    # the preview does not need the SMTP settings
    assert api.get('/admin/mail-templates',
                   headers=auth_headers('admin')).status_code == 200


def test_the_test_send_is_rate_limited(api, auth_headers, sent):
    from limiter import limiter
    admin = auth_headers('admin')
    limiter.enabled = True
    try:
        limiter.reset()
        codes = [api.post('/admin/mail-templates/reset/test',
                          headers=admin).status_code for _ in range(11)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes[:10] == [200] * 10 and codes[10] == 429
