"""Read Blu-ray ISO files through Windows' built-in disk image support."""
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import subprocess

from .jobs import Failure
from .tools import NO_WINDOW


_MOUNT = r"""
$image = $env:DTS_ISO_IMAGE
$owned = $false
try {
    $disk = Get-DiskImage -ImagePath $image
    if (-not $disk.Attached) {
        $disk = Mount-DiskImage -ImagePath $image -StorageType ISO -Access ReadOnly -PassThru
        $owned = $true
    }
    # Windows can take a moment to assign the drive letter after mounting.
    $volume = $null
    for ($i = 0; $i -lt 20 -and -not $volume; $i++) {
        $volume = Get-Volume -DiskImage $disk | Where-Object { $_.DriveLetter } | Select-Object -First 1
        if (-not $volume) { Start-Sleep -Milliseconds 250 }
    }
    if (-not $volume) { throw 'The ISO was mounted without a drive letter.' }
    Write-Output ('DTS_ISO:' + $volume.DriveLetter + ':' + [int]$owned)
} catch {
    if ($owned) { Dismount-DiskImage -ImagePath $image -ErrorAction SilentlyContinue | Out-Null }
    throw
}
"""


def is_iso(source: Path) -> bool:
    return source.suffix.lower() == '.iso' and not source.is_dir()


def _powershell(script: str, image: Path) -> str:
    exe = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = (
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"try {{\n{script}\n}} catch {{\n"
        "    [Console]::WriteLine($_.Exception.Message)\n"
        "    exit 1\n"
        "}\n"
    )
    try:
        result = subprocess.run(
            [str(exe), '-NoProfile', '-NonInteractive', '-Command', command],
            env={**os.environ, 'DTS_ISO_IMAGE': str(image)}, stdin=subprocess.DEVNULL,
            capture_output=True, encoding='utf-8', errors='replace', timeout=60,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure('iso_failed', f'Windows could not access the Blu-ray ISO: {image}\n{exc}', detail=str(exc),
                      path=str(image)) from exc
    if result.returncode:
        detail = result.stdout.strip() or result.stderr.strip()
        raise Failure('iso_failed', f'Windows could not access the Blu-ray ISO: {image}\n{detail}', detail=detail,
                      path=str(image))
    return result.stdout


@contextmanager
def mounted(image: Path):
    if not image.is_file():
        raise FileNotFoundError(f'Blu-ray ISO file not found: {image}')
    if os.name != 'nt':
        raise RuntimeError('Blu-ray ISO import requires Windows.')
    image = image.resolve()
    output = _powershell(_MOUNT, image)
    for line in output.splitlines():
        if line.startswith('DTS_ISO:'):
            _, letter, owned = line.strip().split(':')
            break
    else:
        raise Failure('iso_failed', f'Windows did not return a drive letter for the Blu-ray ISO: {image}',
                      path=str(image))
    try:
        yield Path(f'{letter}:\\')
    finally:
        if owned == '1':
            try:
                _powershell('Dismount-DiskImage -ImagePath $env:DTS_ISO_IMAGE | Out-Null', image)
            except RuntimeError:
                logging.getLogger(__name__).warning('Could not dismount %s', image, exc_info=True)


@contextmanager
def playlist_file(playlist: Path, image: Path | None):
    """Resolve a disc-relative playlist on whichever drive Windows assigns."""
    if image is None:
        yield playlist
        return
    if playlist.parent != Path('BDMV/PLAYLIST') or playlist.suffix.lower() != '.mpls':
        raise ValueError(f'Invalid Blu-ray ISO playlist: {playlist}')
    with mounted(image) as root:
        yield root / playlist
