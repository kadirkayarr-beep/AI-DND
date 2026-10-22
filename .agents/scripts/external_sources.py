"""Explicit external book verification; never downloads or silently skips books."""
import argparse
import hashlib
import json
import os
from pathlib import Path

def source_path(filename, directory=None):
    directory = directory or os.environ.get('AI_DND_REFERENCE_DIR')
    if not directory:
        raise RuntimeError('Set AI_DND_REFERENCE_DIR to the external book directory; see EXTERNAL_SOURCES.md.')
    if Path(filename).name != filename:
        raise ValueError('Expected a plain source filename')
    return Path(directory) / filename

def verify_sources(directory, manifest):
    for entry in manifest:
        path = source_path(entry['filename'], directory)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            header = stream.read(5)
            if header != b'%PDF-':
                raise ValueError('Invalid PDF header: ' + entry['filename'])
            digest.update(header)
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if path.stat().st_size != entry['bytes'] or digest.hexdigest() != entry['sha256']:
            raise ValueError('Source identity mismatch: ' + entry['filename'])
    return len(manifest)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', default=os.environ.get('AI_DND_REFERENCE_DIR'))
    args = parser.parse_args()
    if not args.source_dir:
        parser.error('--source-dir or AI_DND_REFERENCE_DIR is required; external verification was NOT performed')
    manifest = json.loads(Path(__file__).with_name('external-books.json').read_text(encoding='utf-8'))
    print(f'External book identities verified: {verify_sources(args.source_dir, manifest)}/{len(manifest)}')
