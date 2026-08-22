#!/usr/bin/env python3
"""Fetch Slardar issue stack via Avocado API. No SSO needed.
Part of the adk-fetch skill.
"""
import json, sys, re, urllib.parse, urllib.request, urllib.error

API_HOST   = 'https://avocado-api.tiktok-row.net'
PATH_META  = '/api/llmtools/issue/query_meta_info'
PATH_BLAME = '/api/llmtools/issue/query_meta_info_with_blame'
AUTH_KEY   = 'fixed_yoda_auth_key'
TIMEOUT    = 60

def resolve_short(url):
    if not re.search(r'/t/[A-Za-z0-9]+/?$', url):
        return url
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.url
    except Exception:
        return url

def parse_url(url):
    p  = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(p.query)
    frag = p.fragment.lstrip('/').split('?')[0].strip('/').split('/')
    if len(frag) < 4 or frag[0] != 'abnormal' or frag[1] != 'detail':
        raise ValueError(f'Unsupported fragment: {p.fragment}')
    return {
        'aid':        int(qs['aid'][0]),
        'os':         qs['os'][0].strip(),
        'region':     qs['region'][0],
        'issue_type': frag[2],
        'issue_id':   frag[3],
    }

def call_api(path, payload):
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f'{API_HOST}{path}', data=body, method='POST',
        headers={
            'Content-Type': 'application/json',
            'Accept':       'application/json',
            'YODA_AUTH_KEY': AUTH_KEY,
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())

def fmt_frame(f, i):
    mod    = f.get('module') or f.get('lib_name') or f.get('unit') or ''
    meth   = f.get('method') or f.get('symbol') or f.get('func') or '<unknown>'
    fpath  = (f.get('filepath') or f.get('file_path') or
              f.get('source_path') or f.get('filename') or '')
    line   = f.get('linenumber') or f.get('line') or 0
    offset = f.get('location') or f.get('offset') or ''
    loc    = f'{fpath}:{line}' if (fpath and line) else fpath
    suffix = (f' ({loc})' if loc else '') + (f' + {offset}' if offset not in ('', None) else '')
    tag    = ' [sys]' if f.get('is_sys') else ''
    return f'#{i:02d} {mod+" " if mod else ""}{meth}{suffix}{tag}'.strip()

def extract(result, parsed):
    data = result.get('data') or {}
    meta = data.get('meta') or {}
    root = meta if meta else data
    ev   = (root.get('event_meta_info') or root.get('event_detail') or
            data.get('event_meta_info') or data.get('event_detail') or {})
    thr  = ev.get('main_thread') or ev.get('crash_thread') or {}
    bt   = [f for f in (thr.get('backtrace') or []) if isinstance(f, dict)]
    return {
        'request':            parsed,
        'title':              root.get('title') or root.get('issue_title') or data.get('title'),
        'reason':             root.get('reason') or data.get('reason') or thr.get('reason'),
        'extra_crash_reason': root.get('extra_crash_reason') or data.get('extra_crash_reason'),
        'app_version':        root.get('app_version') or data.get('app_version'),
        'commit_id':          root.get('commit_id')    or data.get('commit_id'),
        'thread_name':        thr.get('thread_name'),
        'backtrace_count':    len(bt),
        'backtrace_pretty':   [fmt_frame(f, i) for i, f in enumerate(bt)],
        'backtrace':          bt,
    }

def main():
    url = next((a for a in sys.argv[1:] if not a.startswith('-')), '')
    if not url:
        print(json.dumps({'code': -1, 'msg': 'Usage: slardar_fetch.py <URL> [--blame]'}))
        sys.exit(1)
    try:
        resolved = resolve_short(url)
        parsed   = parse_url(resolved)
        result   = call_api(PATH_META, dict(parsed))
        summary  = extract(result, parsed)
        if summary['backtrace_count'] == 0 and '--blame' not in sys.argv:
            p2 = dict(parsed)
            p2['include_other_threads'] = True
            summary = extract(call_api(PATH_BLAME, p2), parsed)
        print(json.dumps({'code': 0, 'msg': 'ok', 'data': summary}, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({'code': -1, 'msg': str(e)}))
        sys.exit(1)

if __name__ == '__main__':
    main()
