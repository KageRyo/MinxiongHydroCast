import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/protocol_archive.py'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'repository'
    root.mkdir()
    git(root, 'init', '-q')
    for name in [
        'data/samples/event_split_manifest.json',
        'data/samples/event_split_manifest.json.sha256',
        'docs/v0.2_dataset_protocol.md', 'scripts/validate_public_contracts.py',
        'tests/fixtures/wra_iow_latest.json', 'pyproject.toml', 'CITATION.cff', 'LICENSE',
    ]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (root / 'README.md').write_text('committed source\n')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        'commit', '-qm', 'fixture')
    return root


def command(repository, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=repository,
                          capture_output=True, text=True)


def archive_files(path):
    with tarfile.open(path) as archive:
        return {m.name: archive.extractfile(m).read() for m in archive if m.isfile()}


def rewrite_archive(path, files):
    with tarfile.open(path, 'w:gz') as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def test_build_uses_committed_source_and_produces_verifiable_deterministic_archive(repository, tmp_path):
    (repository / 'README.md').write_text('uncommitted private edit\n')
    (repository / '.env').write_text('SECRET=never-include\n')
    (repository / 'data/external').mkdir()
    (repository / 'data/external/raw.json').write_text('private raw')
    first, second = tmp_path / 'first.tar.gz', tmp_path / 'second.tar.gz'
    for output in [first, second]:
        result = command(repository, 'build', '--output', str(output))
        assert result.returncode == 0, result.stderr
    assert first.read_bytes() == second.read_bytes()
    files = archive_files(first)
    assert files['README.md'] == b'committed source\n'
    assert '.env' not in files
    assert 'data/external/raw.json' not in files
    metadata = json.loads(files['PROTOCOL_ARCHIVE.json'])
    assert metadata['source_commit'] == git(repository, 'rev-parse', 'HEAD')
    assert metadata['forecast_publication_ready'] is False
    assert metadata['dataset_milestone_complete'] is False
    assert 'public metadata and test fixtures' in metadata['redistribution']
    extracted = tmp_path / 'verified'
    result = command(repository, 'verify', '--archive', str(first), '--extract-to', str(extracted))
    assert result.returncode == 0, result.stderr
    assert (extracted / 'README.md').read_bytes() == b'committed source\n'


@pytest.mark.parametrize('corruption', ['checksum', 'schema'])
def test_build_rejects_invalid_committed_manifest(repository, tmp_path, corruption):
    manifest = repository / 'data/samples/event_split_manifest.json'
    payload = json.loads(manifest.read_text())
    payload['schema_version'] = 'unsupported'
    manifest.write_text(json.dumps(payload))
    if corruption == 'schema':
        checksum = hashlib.sha256(manifest.read_bytes()).hexdigest()
        manifest.with_suffix('.json.sha256').write_text(f'{checksum}  {manifest.name}\n')
    git(repository, 'add', '.')
    git(repository, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        'commit', '-qm', 'invalid manifest')
    output = tmp_path / 'invalid.tar.gz'
    result = command(repository, 'build', '--output', str(output))
    assert result.returncode != 0
    assert not output.exists()


def test_verify_rejects_tampering_before_extracting(repository, tmp_path):
    output = tmp_path / 'archive.tar.gz'
    assert command(repository, 'build', '--output', str(output)).returncode == 0
    files = archive_files(output)
    files['README.md'] = b'tampered'
    rewrite_archive(output, files)
    destination = tmp_path / 'verified'
    result = command(repository, 'verify', '--archive', str(output), '--extract-to', str(destination))
    assert result.returncode != 0
    assert not destination.exists()


@pytest.mark.parametrize('name,kind', [('../escape', 'file'), ('/absolute', 'file'),
                                      ('link', 'symlink'), ('README.md', 'duplicate')])
def test_verify_rejects_unsafe_members(repository, tmp_path, name, kind):
    output = tmp_path / 'archive.tar.gz'
    assert command(repository, 'build', '--output', str(output)).returncode == 0
    raw = gzip.decompress(output.read_bytes())
    buffer = io.BytesIO(raw)
    with tarfile.open(fileobj=buffer, mode='a') as archive:
        member = tarfile.TarInfo(name)
        if kind == 'symlink':
            member.type = tarfile.SYMTYPE
            member.linkname = '../escape'
        archive.addfile(member)
    output.write_bytes(gzip.compress(buffer.getvalue()))
    destination = tmp_path / 'verified'
    result = command(repository, 'verify', '--archive', str(output), '--extract-to', str(destination))
    assert result.returncode != 0
    assert not destination.exists()
    assert not (tmp_path / 'escape').exists()


def test_verify_never_overwrites_existing_destination(repository, tmp_path):
    output = tmp_path / 'archive.tar.gz'
    assert command(repository, 'build', '--output', str(output)).returncode == 0
    destination = tmp_path / 'existing'
    destination.mkdir()
    sentinel = destination / 'README.md'
    sentinel.write_text('keep existing work')
    result = command(repository, 'verify', '--archive', str(output), '--extract-to', str(destination))
    assert result.returncode != 0
    assert sentinel.read_text() == 'keep existing work'


@pytest.mark.parametrize('name', ['docs/model.pt', 'tests/private/notes.md', 'docs/link'])
def test_build_refuses_restricted_or_linked_source_content(repository, tmp_path, name):
    target = repository / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if name == 'docs/link':
        target.symlink_to('/outside/private')
    else:
        target.write_text('restricted content')
    git(repository, 'add', '.')
    git(repository, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        'commit', '-qm', 'restricted source')
    output = tmp_path / 'source.tar.gz'
    result = command(repository, 'build', '--output', str(output))
    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize('field,value', [('source_commit', 123), ('source_tree', None),
                                        ('forecast_publication_ready', True)])
def test_verify_rejects_invalid_metadata_with_a_concise_error(repository, tmp_path, field, value):
    output = tmp_path / 'source.tar.gz'
    assert command(repository, 'build', '--output', str(output)).returncode == 0
    files = archive_files(output)
    metadata = json.loads(files['PROTOCOL_ARCHIVE.json'])
    metadata[field] = value
    files['PROTOCOL_ARCHIVE.json'] = json.dumps(metadata).encode()
    del files['SHA256SUMS']
    files['SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(content).hexdigest()}  {name}\n'
        for name, content in sorted(files.items())
    ).encode()
    rewrite_archive(output, files)
    destination = tmp_path / 'verified'
    result = command(repository, 'verify', '--archive', str(output), '--extract-to', str(destination))
    assert result.returncode != 0
    assert 'Traceback' not in result.stderr
    assert not destination.exists()


def test_build_rejects_git_option_as_revision(repository, tmp_path):
    output = tmp_path / 'source.tar.gz'
    result = command(repository, 'build', '--ref=--help', '--output', str(output))
    assert result.returncode != 0
    assert not output.exists()


def test_build_rejects_output_outside_workspace_and_temporary_roots(repository):
    result = command(repository, 'build', '--output', '/proc/mhc-forbidden/source.tar.gz')
    assert result.returncode != 0
    assert 'outside permitted' in result.stderr


@pytest.mark.parametrize('action', ['build', 'verify'])
def test_destinations_refuse_dangling_symlinks_without_writing_targets(repository, tmp_path, action):
    target = tmp_path / 'must-not-be-created'
    destination = tmp_path / 'alias'
    destination.symlink_to(target)
    if action == 'build':
        result = command(repository, 'build', '--output', str(destination))
    else:
        archive = tmp_path / 'source.tar.gz'
        assert command(repository, 'build', '--output', str(archive)).returncode == 0
        result = command(repository, 'verify', '--archive', str(archive),
                         '--extract-to', str(destination))
    assert result.returncode != 0
    assert destination.is_symlink()
    assert not target.exists()


def test_verify_refuses_reading_archive_outside_permitted_roots(repository):
    result = command(repository, 'verify', '--archive', '/proc/self/maps')
    assert result.returncode != 0
    assert 'outside permitted' in result.stderr
