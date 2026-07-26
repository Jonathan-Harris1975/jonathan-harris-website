#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.sync_podcast_episodes import parse_feed

FIXTURE=b"""<?xml version='1.0'?><rss xmlns:podcast='https://podcastindex.org/namespace/1.0'><channel><item><title>AI Agent Skills and Model Hype</title><link>https://example.com/episodes/agent-skills</link><description>Practical context without hype.</description><pubDate>Tue, 21 Jul 2026 10:00:00 GMT</pubDate><enclosure url='https://cdn.example.com/agent.mp3'/><podcast:transcript url='https://transcripts.example.com/TT-2026-07-21.html'/></item></channel></rss>"""

def main()->int:
    rows=parse_feed(FIXTURE)
    assert len(rows)==1, rows
    row=rows[0]
    assert row['slug']=='agent-skills', row
    assert row['date']=='2026-07-21', row
    assert row['transcript_url']=='https://jonathan-harris.online/transcripts/TT-2026-07-21.html', row
    assert row['session_id']=='TT-2026-07-21', row
    assert row['audio_url']=='https://cdn.example.com/agent.mp3', row
    print('Podcast RSS fallback parser passed.')
    return 0

if __name__=='__main__': raise SystemExit(main())
