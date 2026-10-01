"""Colorado 14er ingestion, Python 3.10+. No endpoint guessing or fuzzy auto-matches.

Install: pip install requests beautifulsoup4 pandas defusedxml
See project_roadmap.md and the accompanying Colab notebook for execution.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import importlib.metadata
import json
import math
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET

BASE = 'https://www.14ers.com/'
BOT = 'Colorado14erResearch'
MAX_BYTES = 20_000_000
RISK_LABELS = ('Low', 'Moderate', 'Considerable', 'High', 'Extreme')
YDS_ENCODING = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}


class AccessBlocked(RuntimeError):
    pass


class IngestionError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def atomic_bytes(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(body)
    temp.replace(path)


def canonical(url):
    """Only follow same-site HTTPS URLs. Never send cookies to another host."""
    p = urlsplit(html.unescape(urljoin(BASE, url)))
    if p.scheme != 'https' or p.hostname not in ('14ers.com', 'www.14ers.com'):
        raise IngestionError('Unexpected host or non-HTTPS URL')
    if p.username or p.password:
        raise IngestionError('Credentials in URL are not supported')
    if p.port not in (None, 443):
        raise IngestionError('Unexpected port')
    return urlunsplit(('https', 'www.14ers.com', p.path or '/', p.query, ''))


def norm(text):
    text = text.casefold().replace('mt.', 'mount').replace('mt ', 'mount ')
    text = text.replace('mount of the holy cross', 'holy cross')
    text = text.replace('mount evans', 'mount blue sky')
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'\bstandard route\b', ' ', text)
    text = re.sub(r'\bthe\b', ' ', text)
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def explicit_urls(soup, base_url):
    """Extract literal links, including inline JS strings, without executing JS.

    Function-generated URLs are intentionally unresolved, never synthesized.
    """
    values = []
    for node in soup.find_all(True):
        for attr in ('href', 'data-href', 'data-url', 'data-download', 'action'):
            value = node.get(attr)
            if isinstance(value, str):
                values.append(value)
        handler = node.get('onclick', '')
        values.extend(re.findall(r'''["']([^"']+)["']''', handler))
    for script in soup.find_all('script'):
        values.extend(re.findall(r'''["']([^"'\r\n]+)["']''', script.get_text()))
    result = set()
    for value in values:
        value = value.replace('\\/', '/')
        if value.startswith(('javascript:', '#', 'mailto:')):
            continue
        if not re.search(r'(\.php(?:\?|$)|\.gpx(?:\?|$))', value, re.I):
            continue
        if any(c in value for c in (' ', '{', '}', '<', '>')):
            continue
        try:
            result.add(canonical(urljoin(base_url, value)))
        except IngestionError:
            continue
    return sorted(result)


def route_url(url):
    p = urlsplit(url)
    q = parse_qs(p.query)
    if p.path.endswith('/route.php') and len(q.get('route', [])) == 1:
        rid = q['route'][0]
        if re.fullmatch(r'[a-zA-Z0-9_-]+', rid):
            return BASE + 'route.php?' + urlencode({'route': rid})
    return None


class Client:
    def __init__(self, root, contact, cookie_file=None, delay=4.0):
        self.root = Path(root)
        self.cache = self.root / 'cache'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.log = self.root / 'events.jsonl'
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': f'{BOT}/0.1 ({contact})'})
        if cookie_file:
            jar = MozillaCookieJar(str(cookie_file))
            jar.load(ignore_discard=True, ignore_expires=False)
            for cookie in jar:
                if cookie.domain.lstrip('.') in ('14ers.com', 'www.14ers.com'):
                    self.session.cookies.set_cookie(cookie)
        self.delay = max(3.0, delay)
        self.last_request = 0.0
        self.robots = None

    def event(self, **entry):
        # No headers, cookies, passwords, or response bodies in the log.
        with self.log.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'time': now(), **entry}, ensure_ascii=False) + '\n')

    def wait(self):
        remaining = self.delay + random.uniform(0, 1) - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        self.last_request = time.monotonic()

    def check_robots(self):
        """Fail closed if robots cannot be retrieved, except HTTP 404."""
        self.wait()
        try:
            response = self.session.get(BASE + 'robots.txt', timeout=(10, 45),
                                        allow_redirects=False)
        except requests.RequestException as exc:
            raise AccessBlocked('robots.txt unavailable; no crawl started') from exc
        self.robots = RobotFileParser()
        if response.status_code == 404:
            self.robots.parse(['User-agent: *', 'Allow: /'])
        elif response.status_code == 200:
            body = response.text
            if '<html' in body.lower() or 'captcha' in body.lower():
                raise AccessBlocked('robots.txt returned HTML/challenge')
            self.robots.parse(body.splitlines())
        else:
            raise AccessBlocked(f'robots.txt HTTP {response.status_code}; no crawl started')
        for value in (self.robots.crawl_delay(BOT), self.robots.crawl_delay('*')):
            if value:
                self.delay = max(self.delay, float(value))
        rate = self.robots.request_rate(BOT) or self.robots.request_rate('*')
        if rate and rate.requests > 0:
            # Serialize requests rather than burst at the allowed rate.
            self.delay = max(self.delay, rate.seconds / rate.requests)

    def fetch(self, url, refresh=False, referer=None):
        url = canonical(url)
        if self.robots is None:
            raise IngestionError('Call check_robots() before fetch()')
        if not self.robots.can_fetch(BOT, url):
            raise IngestionError('robots.txt disallows this URL')
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / (key + '.bin')
        if path.exists() and not refresh:
            sidecar = self.cache / (key + '.json')
            cached = path.read_bytes()
            metadata = json.loads(sidecar.read_text()) if sidecar.exists() else {}
            if metadata.get('url') == url and metadata.get('sha256') == hashlib.sha256(cached).hexdigest():
                return cached
            self.event(kind='cache_integrity_mismatch', url=url)
        current = url
        redirects = 0
        attempts = 0
        while attempts < 5:
            if not self.robots.can_fetch(BOT, current):
                raise IngestionError('robots.txt disallows redirect destination')
            self.wait()
            try:
                with self.session.get(current, timeout=(10, 60), allow_redirects=False,
                                      stream=True,
                                      headers={'Referer': referer} if referer else {}) as r:
                    status = r.status_code
                    self.event(kind='request', url=current, status=status)
                    if status in (401, 403):
                        raise AccessBlocked(f'HTTP {status}; stop and resolve site access')
                    if status in (301, 302, 303, 307, 308):
                        redirects += 1
                        if redirects > 5 or not r.headers.get('Location'):
                            raise IngestionError('Invalid redirect chain')
                        current = canonical(urljoin(current, r.headers['Location']))
                        if re.search(r'(login|signin)', urlsplit(current).path, re.I):
                            raise AccessBlocked('Login required or session expired')
                        continue
                    if status in (429, 500, 502, 503, 504):
                        attempts += 1
                        wait = 2 ** attempts * 5 + random.uniform(0, 2)
                        retry_after = r.headers.get('Retry-After')
                        if retry_after:
                            try:
                                wait = max(wait, float(retry_after))
                            except ValueError:
                                try:
                                    wait = max(wait, parsedate_to_datetime(retry_after).timestamp() - time.time())
                                except (ValueError, TypeError, OverflowError):
                                    pass
                        self.event(kind='backoff', url=current, seconds=wait)
                        # A very long server cooldown is honored by ending this run.
                        if wait > 300:
                            raise AccessBlocked(f'Server cooldown {wait:.0f}s; rerun later')
                        time.sleep(wait)
                        continue
                    if status != 200:
                        raise IngestionError(f'HTTP {status}')
                    chunks, size = [], 0
                    for chunk in r.iter_content(65536):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise IngestionError('Response exceeds 20 MB cap')
                        chunks.append(chunk)
                    body = b''.join(chunks)
                    prefix = body[:300_000].decode('utf-8', errors='ignore').lower()
                    if any(marker in prefix for marker in (
                        'cf-chl-', 'challenge-platform', 'verify you are human',
                        'checking your browser', 'access denied', 'g-recaptcha')):
                        raise AccessBlocked('Access challenge; no bypass attempted')
                    # Ordinary map verification widgets do not imply the whole
                    # route page is blocked; the metadata/GPX controls may work.
                    if b'<html' in body.lower() and re.search(
                        r'<input[^>]+type\s*=\s*["\']password', prefix):
                        raise AccessBlocked('Login form returned; authorized session required')
                    atomic_bytes(path, body)
                    write_json(self.cache / (key + '.json'), {
                        'url': url, 'final_url': current, 'fetched_at': now(),
                        'sha256': hashlib.sha256(body).hexdigest()})
                    return body
            except (requests.Timeout, requests.ConnectionError):
                attempts += 1
                self.event(kind='network_retry', url=current, attempt=attempts)
                time.sleep(2 ** attempts * 5)
        raise IngestionError('Retry budget exhausted')


def metric_candidates(overview, label, unit):
    """Keep every published total and its label; ambiguity is never first-number wins."""
    section = re.search(label + r'\s+(.*?)(?=Elevation\s+Gain|Length|Difficulty|Exposure|Rockfall|Route[ -]Finding|Commitment|Peak\s+Conditions|Downloads|Route\s+Last\s+Updated|\bGPX\b|\bKML\b|$)', overview, re.I)
    if not section:
        return []
    text = section.group(1)
    # Actual overviews use both prefix labels and suffix labels. A shared unit
    # may follow only the last prefix total (Harvard-Columbia's distance).
    if re.match(r'(?:From|With)\s+', text, re.I) and re.search(unit, text, re.I):
        return [{'value': float(m.group(2).replace(',', '')), 'start_label': m.group(1).strip()}
                for m in re.finditer(r'(?:From|With)\s+([^:]+):\s*([\d,]+(?:\.\d+)?)', text, re.I)]
    matches = list(re.finditer(r'([\d,]+(?:\.\d+)?)\s*' + unit, text, re.I))
    candidates = []
    for i, match in enumerate(matches):
        tail = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
        tail = tail.strip(' :;,()-')
        label_text = re.sub(r'^(?:from|starting at|starting near|if you start at|if you start near)\s+', '', tail, flags=re.I)
        # Explanatory notes are not a start location. Preserve them separately.
        if re.match(r'^(?:via|if you descend)\s+', tail, re.I):
            label_text = tail
        elif not re.match(r'^(?:from|starting at|starting near|if you start at|if you start near)\s+', tail, re.I):
            label_text = ''
        candidates.append({'value': float(match.group(1).replace(',', '')), 'start_label': label_text,
                           **({'scope_note': tail} if tail and not label_text else {})})
    return candidates


def start_norm(text):
    """Start labels retain drive/access qualifiers; parentheses are meaningful."""
    text = re.sub(r'\btrailhead\b', 'th', text.lower())
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def apply_selection_metadata(row, source):
    result = dict(source)
    result['yds_observed_class'] = source.get('yds_class')
    result['yds_effective_provenance'] = source.get('source_url', '')
    override = row.get('yds_class_override', '')
    if override:
        if not row.get('yds_override_provenance') or int(override) not in YDS_ENCODING:
            raise IngestionError('Unsupported or unprovenanced YDS override')
        result['yds_class'] = int(override)
        result['yds_encoded'] = YDS_ENCODING[int(override)]
        result['yds_effective_provenance'] = row['yds_override_provenance']
    unresolved = []
    for field in ('source_distance_mi', 'source_gain_ft'):
        candidates = source.get(field + '_candidates', [])
        if len(candidates) > 1:
            labels = {start_norm(row.get('start_name', ''))}
            if row.get('descent_policy') in ('reverse_ascent', 'West Ridge to Blue Lakes; no Cristo Couloir'):
                labels.add(start_norm('if you descend the ascent route'))
            if row.get('source_url', '').endswith('route=oxfo2') and row.get('start_name') == 'Missouri Gulch':
                labels.add(start_norm('via Belford standard route'))
            selected = [c for c in candidates if start_norm(c['start_label']) in labels and c['start_label']]
            result[field] = selected[0]['value'] if len(selected) == 1 else None
            if len(selected) != 1:
                unresolved.append(field)
        elif candidates:
            label = candidates[0]['start_label']
            # A named single total must also match a named chosen start.
            if label and row.get('start_name') and start_norm(label) != start_norm(row['start_name']):
                result[field] = None
                unresolved.append(field)
    result['metadata_scope_status'] = 'review_required' if unresolved else 'single_or_matched_published_total'
    result['metadata_scope_unresolved_fields'] = unresolved
    return result


def parse_route(body, url):
    soup = BeautifulSoup(body, 'html.parser')
    h1 = soup.find('h1')
    if not h1:
        raise IngestionError('No route heading: HTML layout changed or access denied')
    title = h1.get_text(' ', strip=True)
    # Restrict numeric extraction to the overview, ahead of narrative directions.
    text = soup.get_text(' ', strip=True)
    start = text.find(title)
    overview = text[max(0, start):]
    end = re.search(r'Route Last Updated:', overview)
    if end:
        overview = overview[:end.start()]
    def extract(pattern):
        m = re.search(pattern, overview, re.I)
        return m.group(1) if m else None
    rating = extract(r'Difficulty\s+((?:Easy\s+|Difficult\s+)?Class\s+\d(?:\.\d+[a-d]?)?)')
    number = re.search(r'Class\s+(\d)', rating or '')
    cls = int(number.group(1)) if number else None
    gains = metric_candidates(overview, r'Elevation\s+Gain', r'(?:ft|feet|\')')
    distances = metric_candidates(overview, r'Length(?:\s+Round[ -]Trip)?(?:\s+RT)?', r'mi(?:les)?')
    risk = {}
    for field, label in [('exposure', r'Exposure'),
                         ('rockfall', r'Rockfall(?:\s+Potential)?'),
                         ('route_finding', r'Route[ -]Finding'),
                         ('commitment', r'Commitment')]:
        raw = extract(label + r'\s+(' + '|'.join(RISK_LABELS) + r')\b')
        risk[field + '_raw'] = raw
    gpx = set()
    for link in explicit_urls(soup, url):
        p = urlsplit(link)
        q = parse_qs(p.query)
        if p.path.lower().endswith('.gpx') or any(
            v.lower() == 'gpx' for values in q.values() for v in values):
            gpx.add(link)
    # GPX links may use an opaque PHP endpoint with GPX in control text/image alt.
    for node in soup.find_all(['a', 'button']):
        label = node.get_text(' ', strip=True) + ' ' + ' '.join(
            img.get('alt', '') for img in node.find_all('img'))
        if re.search(r'\bgpx\b', label, re.I):
            miniature = BeautifulSoup(str(node), 'html.parser')
            gpx.update(link for link in explicit_urls(miniature, url)
                       if not urlsplit(link).path.lower().endswith(('.png', '.jpg')))
    gpx.discard(url)
    snow_only = bool(re.search(r'snow[ -]only (?:climb|route)', title + ' ' + overview, re.I))
    snow_only = snow_only or any('snow-only' in str(img.get('alt', '')).lower()
                                 for img in soup.find_all('img'))
    return {'source_url': url, 'source_title': title,
            'source_html_sha256': hashlib.sha256(body).hexdigest(),
            'yds_raw': rating, 'yds_class': cls,
            'yds_encoded': YDS_ENCODING.get(cls),
            'source_distance_mi': distances[0]['value'] if len(distances) == 1 else None,
            'source_gain_ft': gains[0]['value'] if len(gains) == 1 else None,
            'source_distance_mi_candidates': distances,
            'source_gain_ft_candidates': gains,
            'snow_only': snow_only, 'gpx_candidates': sorted(gpx), **risk}


def validate_gpx(body):
    """Validate GPX geometry; don't treat waypoints as a hike or join segments."""
    try:
        root = ET.fromstring(body)
    except Exception as exc:
        raise IngestionError('Download is not safe, parseable GPX XML') from exc
    def tag(node):
        return node.tag.rsplit('}', 1)[-1]
    if tag(root) != 'gpx':
        raise IngestionError('XML root is not gpx (possibly HTML login response)')
    sequences = [node for node in root.iter() if tag(node) in ('trkseg', 'rte')]
    points = []
    signature = []
    sequences_used = 0
    with_elevation = 0
    zero_steps = 0
    max_step_m = 0.0
    horizontal_m = 0.0
    endpoints = []
    for sequence in sequences:
        seq = []
        for node in sequence:
            if tag(node) not in ('trkpt', 'rtept'):
                continue
            try:
                lat, lon = float(node.attrib['lat']), float(node.attrib['lon'])
                if not (math.isfinite(lat) and math.isfinite(lon)
                        and -90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError('invalid coordinate')
                elevation = next((float(child.text) for child in node
                                  if tag(child) == 'ele'), None)
                if elevation is not None and not math.isfinite(elevation):
                    raise ValueError('invalid elevation')
            except (KeyError, ValueError, TypeError) as exc:
                raise IngestionError('Invalid GPX coordinates/elevation') from exc
            seq.append((lat, lon, elevation))
        if len(seq) >= 2:
            sequences_used += 1
            endpoints.append({"start": seq[0], "finish": seq[-1]})
            for a, b in zip(seq, seq[1:]):
                p1, p2 = math.radians(a[0]), math.radians(b[0])
                dp, dl = p2-p1, math.radians(b[1]-a[1])
                hav = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
                d = 6_371_008.8 * 2 * math.asin(math.sqrt(min(1, max(0, hav))))
                zero_steps += d < 0.01
                max_step_m = max(max_step_m, d)
                horizontal_m += d
            points.extend(seq)
            # Excludes timestamps and preserves sequence boundaries/order.
            signature.append([(round(a, 6), round(b, 6),
                               round(c, 1) if c is not None else None) for a,b,c in seq])
            with_elevation += sum(c is not None for _,_,c in seq)
    if not points:
        raise IngestionError('GPX has no track/route sequence with at least 2 points')
    # Broad regional check, not proof of route identity.
    if not all(36.8 <= a <= 41.2 and -109.2 <= b <= -101.8 for a,b,_ in points):
        raise IngestionError('Track falls outside broad Colorado bounds')
    return {'point_count': len(points), 'sequence_count': sequences_used,
            'elevation_coverage': with_elevation / len(points),
            'zero_length_steps': zero_steps, 'max_horizontal_step_m': max_step_m,
            'track_horizontal_distance_mi': horizontal_m / 1609.344,
            'sequence_endpoints': endpoints,
            'geometry_sha256': hashlib.sha256(json.dumps(signature).encode()).hexdigest(),
            'gpx_sha256': hashlib.sha256(body).hexdigest()}


def load_manifest(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 100 or len({r['route_id'] for r in rows}) != 100:
        raise ValueError('Manifest must contain exactly 100 unique route IDs')
    if {int(r['selection_number']) for r in rows} != set(range(1, 101)):
        raise ValueError('Selection numbers must be exactly 1..100')
    return rows


def discover(client, refresh=False):
    """Index -> advertised peak route lists -> advertised route detail URLs."""
    body = client.fetch(BASE + 'routes.php', refresh=refresh)
    soup = BeautifulSoup(body, 'html.parser')
    urls = explicit_urls(soup, BASE + 'routes.php')
    peak_lists = sorted({u for u in urls if urlsplit(u).path.endswith('/routelist.php')
                         and 'peakid' in parse_qs(urlsplit(u).query)})
    route_urls = {route_url(u) for u in urls if route_url(u)}
    if not peak_lists and not route_urls:
        raise IngestionError('Route index exposes no route links; inspect cached HTML')
    for url in peak_lists:
        try:
            page = BeautifulSoup(client.fetch(url, refresh=refresh), 'html.parser')
            route_urls.update(route_url(u) for u in explicit_urls(page, url) if route_url(u))
        except AccessBlocked:
            raise
        except (IngestionError, requests.RequestException) as exc:
            client.event(kind='discovery_error', url=url, message=str(exc))
    catalog = []
    for url in sorted(route_urls):
        try:
            catalog.append(parse_route(client.fetch(url, refresh=refresh), url))
        except AccessBlocked:
            # Save already discovered metadata before stopping the entire site crawl.
            write_json(client.root / 'catalog.partial.json', catalog)
            raise
        except (IngestionError, requests.RequestException) as exc:
            client.event(kind='catalog_error', url=url, message=str(exc))
    write_json(client.root / 'catalog.json', catalog)
    return catalog


def choose(row, catalog):
    """Source URL overrides are explicit. Otherwise only exact normalized names."""
    if row.get('source_url', '').strip():
        url = route_url(canonical(row['source_url']))
        if not url:
            raise IngestionError('source_url must be an explicit route.php?route=... URL')
        entries = [r for r in catalog if r['source_url'] == url]
    else:
        names = [row.get('canonical_name', ''), row['requested_name']] + row.get('match_names', '').split('|')
        keys = {norm(n) for n in names if n.strip()}
        entries = [r for r in catalog if norm(r['source_title']) in keys]
    if len(entries) == 1:
        return entries[0], []
    options = entries or sorted(catalog, key=lambda r: difflib.SequenceMatcher(
        None, norm(row['requested_name']), norm(r['source_title'])).ratio(), reverse=True)[:5]
    candidates = [{'title': r['source_title'], 'url': r['source_url']} for r in options]
    return None, candidates


def load_curated(path, manifest):
    """Validate an owner-approved local export without issuing network requests."""
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    digest = hashlib.sha256(Path(manifest).read_bytes()).hexdigest()
    if document.get('manifest_sha256') != digest or document.get('schema_version') != '1.0.0':
        raise IngestionError('Curated export schema/frozen manifest mismatch')
    if not isinstance(document.get('records'), list) or not document.get('permission_evidence'):
        raise IngestionError('Curated export requires records and permission evidence')
    records = {}
    ids = {r['route_id'] for r in load_manifest(manifest)}
    for record in document['records']:
        if not isinstance(record, dict):
            raise IngestionError('Curated records must be JSON objects')
        rid = record.get('route_id')
        if rid not in ids or rid in records:
            raise IngestionError('Unknown or duplicate curated route ID')
        records[rid] = record
    return document, records


def ingest_curated(row, record, document, export_path, root):
    """A curation adapter, not a trip-report scraping or inferred geometry adapter."""
    required = ('reviewer', 'review_date', 'metadata_evidence', 'geometry_evidence',
                'source_references', 'start_name', 'summit_order', 'descent_policy',
                'start_policy', 'yds_raw', 'gpx_file', 'gpx_sha256')
    if any(not record.get(k) for k in required):
        raise IngestionError('Curated record lacks required review/provenance fields')
    datetime.strptime(record['review_date'], '%Y-%m-%d')
    if not isinstance(record['source_references'], list) or any(
            not isinstance(u, str) or urlsplit(u).scheme != 'https' or not urlsplit(u).hostname
            for u in record['source_references']):
        raise IngestionError('Curated source references must be HTTPS URLs')
    for field in ('summit_order', 'descent_policy', 'start_policy'):
        if record[field] != row[field]:
            raise IngestionError('Curated itinerary differs from frozen manifest: ' + field)
    if row.get('start_name') and norm(row['start_name']) != norm(record['start_name']):
        raise IngestionError('Curated start differs from frozen manifest')
    for field in ('itinerary_verified', 'dry_summer_verified'):
        if type(record.get(field)) is not bool:
            raise IngestionError('Curated verification fields must be JSON booleans')
    if record['dry_summer_verified'] and not record.get('conditions_evidence'):
        raise IngestionError('Dry-summer verification requires conditions evidence')
    cls = record.get('yds_class')
    if type(cls) is not int or cls not in YDS_ENCODING:
        raise IngestionError('Invalid curated YDS class')
    raw_class = re.search(r'Class\s+([1-5])\b', record['yds_raw'], re.I)
    if not raw_class or int(raw_class.group(1)) != cls:
        raise IngestionError('Curated raw YDS and observed class disagree; use an explicit override')
    values = {}
    for field in ('source_distance_mi', 'source_gain_ft'):
        value = record.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise IngestionError('Invalid positive curated metric: ' + field)
        values[field] = value
    for field in ('exposure_raw', 'rockfall_raw', 'route_finding_raw', 'commitment_raw'):
        if record.get(field) not in RISK_LABELS:
            raise IngestionError('Unknown or missing curated risk: ' + field)
        values[field] = record[field]
    base = Path(export_path).resolve().parent
    relative = Path(record['gpx_file'])
    source_path = (base / relative).resolve()
    if relative.is_absolute() or base not in source_path.parents:
        raise IngestionError('Curated GPX must be inside its export directory')
    if source_path.stat().st_size > MAX_BYTES:
        raise IngestionError('Curated GPX exceeds size cap')
    body = source_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != record['gpx_sha256']:
        raise IngestionError('Curated GPX checksum mismatch')
    quality = validate_gpx(body)
    source = {**values, 'yds_raw': record['yds_raw'], 'yds_class': cls,
              'yds_encoded': YDS_ENCODING[cls], 'snow_only': False,
              'source_url': row.get('source_url', '')}
    row.update(apply_selection_metadata(row, source))
    path = Path(root) / 'gpx' / (row['route_id'] + '.gpx')
    atomic_bytes(path, body)
    provenance = {k: record[k] for k in required if k != 'gpx_file'}
    provenance.update(permission_evidence=document['permission_evidence'],
                      export_sha256=hashlib.sha256(Path(export_path).read_bytes()).hexdigest(),
                      validated_at=now(), **quality)
    write_json(path.with_suffix('.json'), provenance)
    row.update(quality, status='downloaded', gpx_path=str(path), metadata_complete=True,
               start_name=record['start_name'], ingestion_method='approved_local_export',
               curation_provenance=provenance,
               itinerary_verified=str(record['itinerary_verified']).lower(),
               dry_summer_verified=str(record['dry_summer_verified']).lower())


def export(root, results, catalog, run_error=None):
    """All 100 statuses are exported, even after a global access block."""
    root = Path(root)
    groups = defaultdict(list)
    for r in results:
        if r.get('geometry_sha256'):
            groups[r['geometry_sha256']].append(r['route_id'])
    duplicates = [ids for ids in groups.values() if len(ids) > 1]
    # Connected groups preserve transitive links between source aliases,
    # predeclared related itineraries and newly discovered shared geometry.
    parent = {r['route_id']: r['route_id'] for r in results}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(ids):
        ids = [i for i in ids if i in parent]
        for i in ids[1:]:
            parent[find(i)] = find(ids[0])
    source_groups = defaultdict(list)
    for r in results:
        if r.get('source_url'):
            source_groups[r['source_url']].append(r['route_id'])
        join(r.get('related_itinerary_group', '').split('|'))
    for ids in list(groups.values()) + list(source_groups.values()):
        join(ids)
    connected = defaultdict(list)
    for i in parent:
        connected[find(i)].append(i)
    for r in results:
        others = groups.get(r.get('geometry_sha256'), [])
        r['duplicate_geometry_ids'] = '|'.join(i for i in others if i != r['route_id'])
        r['evaluation_group'] = '|'.join(sorted(connected[find(r['route_id'])]))
        r['training_eligible'] = bool(r['status'] == 'downloaded'
                                     and r.get('dry_summer_verified', '').lower() == 'true'
                                     and r.get('itinerary_verified', '').lower() == 'true'
                                     and not r.get('snow_only')
                                     and r.get('yds_encoded') is not None
                                     and r.get('elevation_coverage') == 1.0
                                     and r.get('metadata_complete'))
    # CSV stores candidate lists as JSON instead of Python repr strings.
    frame = pd.DataFrame([{k: json.dumps(v) if isinstance(v, (list,dict)) else v
                           for k,v in r.items()} for r in results])
    for name, subset in [('route_status.csv', frame),
                         ('missing_routes.csv', frame[frame.status != 'downloaded']),
                         ('review_required.csv', frame[(frame.status != 'downloaded') | ~frame.training_eligible |
                                                       (frame.duplicate_geometry_ids != '')])]:
        atomic_bytes(root / name, subset.to_csv(index=False).encode('utf-8'))
    statuses = frame.status.value_counts().to_dict()
    eligible = int(frame.training_eligible.sum())
    report = {'run_time': now(), 'requested': 100, 'catalog_routes': len(catalog),
              'statuses': statuses, 'downloaded': statuses.get('downloaded', 0),
              'training_eligible': eligible, 'duplicate_geometry_groups': duplicates,
              'complete_100_selections_dry_routes': eligible == 100,
              'complete_100_unique_dry_routes': eligible == 100 and not duplicates,
              'run_error': run_error}
    write_json(root / 'run_summary.json', report)
    return report


def ingest_browser_downloads(rows, download_dir, root):
    """Import normal UI downloads; acquisition never implies reviewed itinerary scope."""
    folder = Path(download_dir).resolve()
    ledger = json.loads((folder / 'download_ledger.json').read_text())
    records = {}
    for receipt in ledger:
        code = receipt.get('code', '')
        if not re.fullmatch(r'[a-z0-9_]+', code) or code in records:
            raise IngestionError('Invalid or duplicate browser receipt code')
        if receipt.get('agreement') != 'user_approved_displayed_terms_2026-09-30':
            raise IngestionError('Browser receipt lacks recorded user acceptance')
        if not receipt.get('downloaded_at') or not receipt.get('method', '').startswith('normal_browser_GPX'):
            raise IngestionError('Browser receipt lacks acquisition provenance')
        body = (folder / (code + '.gpx')).read_bytes()
        quality = validate_gpx(body)
        if quality['gpx_sha256'] != receipt.get('gpx_sha256'):
            raise IngestionError('Browser GPX receipt hash mismatch: ' + code)
        records[code] = receipt
    catalog = []
    sources = {}
    for row in rows:
        url = row.get('source_url')
        if not url or url in sources:
            continue
        code = parse_qs(urlsplit(url).query).get('route', [''])[0]
        receipt = records.get(code)
        if not receipt or canonical(receipt['url']) != canonical(url):
            continue
        body = (folder / (code + '_metadata.html')).read_bytes()
        if hashlib.sha256(body).hexdigest() != receipt.get('metadata_sha256'):
            raise IngestionError('Browser metadata receipt hash mismatch: ' + code)
        source = parse_route(body, url)
        sources[url] = (code, source)
        catalog.append(source)
    for row in rows:
        if row.get('status') != 'pending':
            continue
        if row.get('source_url') not in sources:
            row.update(status='awaiting_curation', error='No exact reviewed full-itinerary browser record')
            continue
        code, source = sources[row['source_url']]
        receipt = records[code]
        body = (folder / (code + '.gpx')).read_bytes()
        quality = validate_gpx(body)
        path = root / 'gpx' / (row['route_id'] + '.gpx')
        atomic_bytes(path, body)
        row.update(apply_selection_metadata(row, source), **quality,
                   ingestion_method='normal_browser_download_import', status='downloaded',
                   gpx_path=str(path), coverage_status='unreviewed_source_geometry',
                   coverage_note='Original source track; not certified as complete selected itinerary')
        endpoints = quality['sequence_endpoints']
        first, last = endpoints[0]['start'], endpoints[-1]['finish']
        lat1, lat2 = math.radians(first[0]), math.radians(last[0])
        h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(last[1]-first[1])/2)**2
        row['endpoint_gap_m'] = 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, h)))
        total = row.get('source_distance_mi')
        row['source_track_distance_ratio'] = quality['track_horizontal_distance_mi']/total if total else None
        # These are review priorities, not automatic coverage certifications.
        row['coverage_review_priority'] = (
            'shared_approach_and_summit_connector' if row['route_id'] == 'co14-058' else
            'approach_and_return' if row['start_policy'].startswith('Needleton') else
            'loop_or_traverse_return' if row['itinerary_type'] != 'out_and_back' else
            'start_and_same_path_return' if row['endpoint_gap_m'] > 500 else
            'closed_track_identity_and_scope')
        row['metadata_complete'] = all(row.get(f) is not None for f in (
            'yds_raw', 'source_distance_mi', 'source_gain_ft',
            'exposure_raw', 'rockfall_raw', 'route_finding_raw', 'commitment_raw'))
        write_json(path.with_suffix('.json'), {
            'route_id': row['route_id'], 'source_url': source['source_url'],
            'acquisition_receipt': receipt, 'source_html_sha256': source['source_html_sha256'],
            'validated_at': now(), 'coverage_status': row['coverage_status'],
            'endpoint_gap_m': row['endpoint_gap_m'],
            'source_track_distance_ratio': row['source_track_distance_ratio'],
            'coverage_review_priority': row['coverage_review_priority'], **quality})
    write_json(root / 'catalog.json', catalog)
    return catalog


def run(manifest, out, contact, source_permission_confirmed=False,
        download_agreement_accepted=False, cookie_file=None, refresh=False,
        curated_file=None, offline=False, only_routes=None, browser_download_dir=None):
    rows = load_manifest(manifest)
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    atomic_bytes(root / 'manifest_snapshot.csv', Path(manifest).read_bytes())
    write_json(root / 'run_provenance.json', {
        'started_at': now(), 'manifest_sha256': hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
        'ingestion_version': '2.1.1', 'offline': offline,
        'browser_download_import': bool(browser_download_dir),
        'selected_routes': only_routes or [r['route_id'] for r in rows],
        'source_permission_confirmed': source_permission_confirmed,
        'download_agreement_accepted': download_agreement_accepted,
        'curated_export_supplied': bool(curated_file),
        'python_version': sys.version.split()[0],
        'dependencies': {name: importlib.metadata.version(name) for name in
                         ('requests', 'beautifulsoup4', 'pandas', 'defusedxml')},
    })
    results = [{**r, 'status': 'pending', 'error': '', 'candidates': [],
                'yds_observed_class': None, 'yds_class': None, 'yds_encoded': None} for r in rows]
    if only_routes and not set(only_routes).issubset({r['route_id'] for r in rows}):
        raise ValueError('Unknown smoke-test route ID')
    for r in results:
        if only_routes and r['route_id'] not in only_routes:
            r.update(status='not_selected', error='Outside requested smoke-test subset')
    catalog = []
    error = None
    if browser_download_dir:
        if curated_file or not offline:
            raise ValueError('Browser import requires offline mode and no curated export')
        catalog = ingest_browser_downloads(results, browser_download_dir, root)
        return export(root, results, catalog)
    if curated_file:
        try:
            document, records = load_curated(curated_file, manifest)
            for r in results:
                if r['status'] != 'pending' or r['route_id'] not in records:
                    continue
                try:
                    ingest_curated(r, records[r['route_id']], document, curated_file, root)
                except (IngestionError, ValueError, OSError, TypeError) as exc:
                    r.update(status='curation_error', error=str(exc))
        except (IngestionError, ValueError, OSError, TypeError) as exc:
            for r in results:
                if r['status'] == 'pending':
                    r.update(status='curation_error', error=str(exc))
            return export(root, results, catalog, str(exc))
    if offline:
        for r in results:
            if r['status'] == 'pending':
                r.update(status='awaiting_approved_export', error='No reviewed local export record supplied')
        return export(root, results, catalog)
    if not source_permission_confirmed or not download_agreement_accepted:
        for r in results:
            if r['status'] == 'pending':
                r.update(status='not_started', error='Confirm source permission and download agreement before execution')
        return export(root, results, catalog, 'Execution confirmations required')
    client = Client(root, contact, cookie_file=cookie_file)
    try:
        client.check_robots()
        pending = [r for r in results if r['status'] == 'pending']
        # Frozen mappings make a full 159-route source crawl unnecessary.
        if any(not r.get('source_url') and not r.get('source_review_status', '').endswith('requires_curation')
               and not r.get('source_review_status', '').endswith('requires_assembly') for r in pending):
            catalog = discover(client, refresh=refresh)
        # Explicit route mappings not present in the index are still usable.
        extra = {route_url(canonical(r['source_url'])) for r in pending if r.get('source_url')}
        for url in sorted(u for u in extra if u and u not in {c['source_url'] for c in catalog}):
            try:
                catalog.append(parse_route(client.fetch(url, refresh=refresh), url))
            except (IngestionError, ValueError, requests.RequestException) as exc:
                client.event(kind='catalog_error', url=url, message=str(exc))
        write_json(root / 'catalog.json', catalog)
        for r in results:
            if r['status'] != 'pending':
                continue
            try:
                if not r.get('source_url') and r.get('source_review_status', '').endswith(('requires_curation', 'requires_assembly')):
                    r.update(status='awaiting_curation', error='Reviewed full-itinerary metadata and local geometry required')
                    continue
                source, candidates = choose(r, catalog)
                r['candidates'] = candidates
                if source is None:
                    r.update(status='unresolved', error='No unique exact match; review candidates and update manifest')
                    continue
                r.update(apply_selection_metadata(r, source), ingestion_method='live_source')
                r['metadata_complete'] = all(r.get(f) is not None for f in (
                    'yds_raw', 'source_distance_mi', 'source_gain_ft',
                    'exposure_raw', 'rockfall_raw', 'route_finding_raw', 'commitment_raw'))
                if r['snow_only']:
                    r.update(status='excluded_snow_only', error='Incompatible with dry-summer scope')
                    continue
                links = [canonical(r['gpx_url'])] if r.get('gpx_url') else source['gpx_candidates']
                if len(links) != 1:
                    r.update(status='gpx_link_unresolved', error=f'{len(links)} GPX URLs found; explicit GPX mapping required')
                    continue
                url = links[0]
                path = root / 'gpx' / (r['route_id'] + '.gpx')
                previous = path.read_bytes() if path.exists() and not refresh else None
                # Only resume a local file if its sidecar proves URL provenance.
                sidecar = path.with_suffix('.json')
                prior = json.loads(sidecar.read_text()) if sidecar.exists() else {}
                valid_previous = (previous is not None and prior.get('gpx_url') == url
                                  and prior.get('gpx_sha256') == hashlib.sha256(previous).hexdigest())
                body = previous if valid_previous else client.fetch(
                    url, refresh=refresh, referer=source['source_url'])
                quality = validate_gpx(body)
                atomic_bytes(path, body)
                write_json(sidecar, {'route_id': r['route_id'], 'source_url': source['source_url'],
                                    'gpx_url': url, 'validated_at': now(), **quality})
                r.update(quality, status='downloaded', gpx_url=url, gpx_path=str(path))
                client.event(kind='downloaded', route_id=r['route_id'], sha256=quality['gpx_sha256'])
            except AccessBlocked:
                raise
            except (IngestionError, ValueError, OSError, requests.RequestException) as exc:
                r.update(status='error', error=str(exc))
                client.event(kind='route_error', route_id=r['route_id'], message=str(exc))
            finally:
                export(root, results, catalog)
    except (AccessBlocked, IngestionError, requests.RequestException, ValueError, OSError) as exc:
        error = str(exc)
        for r in results:
            if r['status'] == 'pending':
                r.update(status='blocked_or_not_attempted', error=error)
        client.event(kind='run_stopped', message=error)
    finally:
        report = export(root, results, catalog, error)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='route_manifest.csv')
    parser.add_argument('--out', default='data/raw')
    parser.add_argument('--contact', required=True, help='Your research contact or project URL')
    parser.add_argument('--cookie-file', help='Private Netscape cookie file; never commit it')
    parser.add_argument('--source-permission-confirmed', action='store_true')
    parser.add_argument('--download-agreement-accepted', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--curated-file', help='Reviewed approved-export JSON; GPX paths relative to it')
    parser.add_argument('--browser-download-dir', help='Private normal-browser downloads and hashed receipts; offline only')
    parser.add_argument('--offline', action='store_true', help='Only ingest approved local export; no network')
    parser.add_argument('--only-routes', nargs='+', help='Smoke-test subset; still reports all 100 selections')
    args = parser.parse_args()
    summary = run(args.manifest, args.out, args.contact,
                  args.source_permission_confirmed, args.download_agreement_accepted,
                  args.cookie_file, args.refresh, args.curated_file, args.offline, args.only_routes, args.browser_download_dir)
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary['complete_100_selections_dry_routes'] else 2)
