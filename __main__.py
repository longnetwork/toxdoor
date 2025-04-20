#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, requests


if __name__ == '__main__':
    """
        Обновление ресурсов

        python -m toxdor -h
        
    """
    BOOTSTRAP_FILE = 'bootstrap.txt'
    BOOTSTRAP_LINK = 'https://nodes.tox.chat/'

    import argparse
    
    parser = argparse.ArgumentParser(description="ToxDoor Tools", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    subparsers = parser.add_subparsers(dest='command', help="See help: command -h")
    if subparsers:
        _bootstrap = subparsers.add_parser('bootstrap', description="Download Bootstrap Nodes")
        _bootstrap.add_argument('link', type=str, nargs='?', default=BOOTSTRAP_LINK, help="Bootstrap Nodes Link")

    args = parser.parse_args()

    if args.command == 'bootstrap':
        BOOTSTRAP_LINK = args.link or BOOTSTRAP_LINK
        print(f"{BOOTSTRAP_LINK=}")

        with requests.get(BOOTSTRAP_LINK, timeout=(6, 60)) as rx:
            html = (rx.text or '').strip()

        if html:
            m: list = re.findall(
                (r'(?s)'
                 r'<td>(?P<ipv4>[^<>]+)</td>.*?'
                 r'<td>(?P<ipv6>[^<>]+)</td>.*?'
                 r'<td>(?P<port>[^<>]+)</td>.*?'
                 r'<td>(?P<pubkey>[0-9a-fA-F]{64})</td>.*?'
                 r'<td>(?P<maintainer>[^<>]+)</td>'),
                html,
            )
            if m:
                with open(BOOTSTRAP_FILE, 'w', encoding="utf-8") as f:
                    for l in m:
                        f.write('\t'.join(l) + '\n')


                











        
