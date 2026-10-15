#!/usr/bin/env python3
"""Build and verify a committed, credential-free dataset-protocol source archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_public_contracts import validate_public_manifest  # noqa: E402

REQUIRED = {
    'data/samples/event_split_manifest.json',
    'data/samples/event_split_manifest.json.sha256',
    'docs/v0.2_dataset_protocol.md', 'scripts/validate_public_contracts.py',
    'tests/fixtures/wra_iow_latest.json', 'pyproject.toml', 'CITATION.cff', 'LICENSE',
}
ROOT_FILES = {
    'README.md', 'LICENSE', 'CITATION.cff', 'CHANGELOG.md', 'CONTRIBUTING.md',
    'SECURITY.md', 'pyproject.toml', 'pyrightconfig.json', 'mkdocs.yml',
    'requirements-docs.txt', 'requirements-docs.lock', 'requirements-protocol.lock',
}
METADATA_NAME = 'PROTOCOL_ARCHIVE.json'
GENERATED = {METADATA_NAME, 'SHA256SUMS'}
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 10000


def checked_output_path(path: Path) -> Path:
    if os.path.lexists(path):
        raise FileExistsError('output destination already exists')
    resolved = path.resolve()
    roots = [Path.cwd().resolve(), Path(tempfile.gettempdir()).resolve()]
    if os.environ.get('RUNNER_TEMP'):
        roots.append(Path(os.environ['RUNNER_TEMP']).resolve())
    if not any(resolved.is_relative_to(root) for root in roots):
        raise ValueError('outside permitted output roots: checkout and temporary directories')
    return resolved


def selected(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return (name in ROOT_FILES or (parts and parts[0] in {'src', 'tests', 'docs', 'scripts'})
            or name.startswith('data/samples/'))


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and path.as_posix() == name and not (
        any(part in {'..', '.env', '.git', 'private', '__pycache__'} for part in path.parts)
        or path.suffix.lower() in {'.pt', '.pth', '.ckpt', '.onnx', '.npz', '.npy'}
        or '\\' in name or '\n' in name or '\r' in name
    )


def validate_inputs(files: dict[str, bytes]) -> None:
    missing = REQUIRED - files.keys()
    if missing:
        raise ValueError(f'missing protocol inputs: {sorted(missing)}')
    with tempfile.TemporaryDirectory(prefix='mhc-manifest-') as temporary:
        root = Path(temporary)
        manifest = root / 'event_split_manifest.json'
        checksum = root / 'event_split_manifest.json.sha256'
        manifest.write_bytes(files['data/samples/event_split_manifest.json'])
        checksum.write_bytes(files['data/samples/event_split_manifest.json.sha256'])
        validate_public_manifest(manifest_path=manifest, checksum_path=checksum)


def checksums(files: dict[str, bytes]) -> bytes:
    return ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n'
                   for name, data in sorted(files.items())).encode()


def build(output: Path, ref: str) -> None:
    output = checked_output_path(output)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', ref):
        raise ValueError('revision must be a commit hash or a branch/tag name')
    def git(*args: str) -> bytes:
        return subprocess.check_output(['git', *args])

    revision = git('rev-parse', '--verify', '--end-of-options', f'{ref}^{{commit}}').decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Git did not return a full commit hash')
    tree = git('rev-parse', f'{revision}^{{tree}}').decode().strip()
    files = {}
    with tarfile.open(fileobj=io.BytesIO(git('archive', '--format=tar', revision))) as source:
        for member in source:
            if member.isdir() or not selected(member.name):
                continue
            if not safe_name(member.name) or not member.isfile():
                raise ValueError(f'unsafe source member: {member.name}')
            content = source.extractfile(member)
            assert content is not None
            files[member.name] = content.read()
    validate_inputs(files)
    metadata = {
        'schema_version': 1, 'source_commit': revision, 'source_tree': tree,
        'artifact_kind': 'dataset_protocol_source',
        'dataset_milestone_complete': False, 'forecast_publication_ready': False,
        'redistribution': 'Committed code, documentation and synthetic fixtures only; '
                          'official captures, tensors, checkpoints and private evidence excluded.',
        'verify_command': 'python scripts/validate_public_contracts.py',
        'synthetic_tests': ['tests/test_event_splits.py', 'tests/test_dataset_build.py',
                            'tests/test_radar_tensor_conversion.py',
                            'tests/test_qpe_gauge_validation.py'],
    }
    files[METADATA_NAME] = (json.dumps(metadata, indent=2, sort_keys=True)+'\n').encode()
    files['SHA256SUMS'] = checksums(files)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    payload = gzip.compress(buffer.getvalue(), mtime=0)
    # Verify exactly what will be written before exposing a successful artifact.
    verify_bytes(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as destination:
        destination.write(payload)
    print(f'[OK] protocol source archive built commit={revision} files={len(files)}')


def verify_bytes(payload: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    size = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r|gz') as archive:
        for member in archive:
            if (not safe_name(member.name) or not member.isfile()
                    or member.name in files or not (selected(member.name)
                                                    or member.name in GENERATED)):
                raise ValueError(f'unsafe or duplicate archive member: {member.name}')
            size += member.size
            if size > MAX_BYTES or len(files) >= MAX_FILES:
                raise ValueError('protocol archive exceeds verification limits')
            content = archive.extractfile(member)
            assert content is not None
            files[member.name] = content.read()
    if GENERATED - files.keys():
        raise ValueError('missing archive metadata or checksums')
    expected = files.pop('SHA256SUMS')
    if expected != checksums(files):
        raise ValueError('archive checksum inventory mismatch')
    metadata = json.loads(files[METADATA_NAME])
    if not isinstance(metadata, dict):
        raise ValueError('invalid protocol archive metadata')
    if (metadata.get('schema_version') != 1
            or metadata.get('artifact_kind') != 'dataset_protocol_source'
            or metadata.get('dataset_milestone_complete') is not False
            or metadata.get('forecast_publication_ready') is not False
            or any(not isinstance(metadata.get(field), str)
                   or not re.fullmatch(r'[0-9a-f]{40}', metadata[field])
                   for field in ('source_commit', 'source_tree'))):
        raise ValueError('invalid protocol archive metadata')
    validate_inputs(files)
    files['SHA256SUMS'] = expected
    return files


def verify(archive: Path, extract_to: Path | None) -> None:
    if archive.stat().st_size > MAX_BYTES:
        raise ValueError('compressed protocol archive exceeds verification limits')
    files = verify_bytes(archive.read_bytes())
    if extract_to is not None:
        extract_to = checked_output_path(extract_to)
        # Validation completes before any extraction; mkdir refuses existing paths and symlinks.
        extract_to.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            target = (extract_to / name).resolve()
            if not target.is_relative_to(extract_to):
                raise ValueError('archive member escapes the extraction directory')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as destination:
                destination.write(data)
    print(f'[OK] protocol archive verified files={len(files)}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    builder = commands.add_parser('build', help='Archive allowlisted files from an immutable commit.')
    builder.add_argument('--ref', default='HEAD')
    builder.add_argument('--output', type=Path, required=True)
    verifier = commands.add_parser('verify', help='Validate checksums and inputs before extraction.')
    verifier.add_argument('--archive', type=Path, required=True)
    verifier.add_argument('--extract-to', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            build(args.output, args.ref)
        else:
            verify(args.archive, args.extract_to)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'[ERROR] {error}\n')


if __name__ == '__main__':
    main()
