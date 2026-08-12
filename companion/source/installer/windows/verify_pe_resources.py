#!/usr/bin/env python3
"""Verify deterministic Windows resources embedded in KeystoneLens PE files."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

RT_ICON = 3
RT_GROUP_ICON = 14
RT_VERSION = 16
RT_MANIFEST = 24


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from('<H', data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def pe_layout(data: bytes):
    if data[:2] != b'MZ':
        raise AssertionError('missing MZ header')
    pe = u32(data, 0x3C)
    if data[pe:pe + 4] != b'PE\0\0':
        raise AssertionError('missing PE signature')
    coff = pe + 4
    nsections = u16(data, coff + 2)
    opt_size = u16(data, coff + 16)
    opt = coff + 20
    if u16(data, opt) != 0x20B:
        raise AssertionError('expected PE32+ executable')
    resource_rva = u32(data, opt + 112 + 2 * 8)
    resource_size = u32(data, opt + 112 + 2 * 8 + 4)
    security_off = u32(data, opt + 112 + 4 * 8)
    security_size = u32(data, opt + 112 + 4 * 8 + 4)
    sections = []
    table = opt + opt_size
    for i in range(nsections):
        off = table + i * 40
        name = data[off:off + 8].split(b'\0', 1)[0].decode('ascii', errors='replace')
        vsize = u32(data, off + 8)
        va = u32(data, off + 12)
        raw_size = u32(data, off + 16)
        raw_ptr = u32(data, off + 20)
        sections.append((name, va, vsize, raw_ptr, raw_size))
    return resource_rva, resource_size, security_off, security_size, sections


def rva_to_offset(rva: int, sections) -> int:
    for _name, va, vsize, raw_ptr, raw_size in sections:
        span = max(vsize, raw_size)
        if va <= rva < va + span:
            return raw_ptr + (rva - va)
    raise AssertionError(f'RVA 0x{rva:x} is outside sections')


def resource_leaves(data: bytes, base_off: int, sections):
    leaves = {}

    def walk(dir_rel: int, path: tuple[int, ...]):
        off = base_off + dir_rel
        named = u16(data, off + 12)
        ids = u16(data, off + 14)
        cursor = off + 16
        for _ in range(named + ids):
            name = u32(data, cursor)
            target = u32(data, cursor + 4)
            cursor += 8
            if name & 0x80000000:
                raise AssertionError('named resources are not expected')
            ident = name & 0xFFFF_FFFF
            if target & 0x80000000:
                walk(target & 0x7FFF_FFFF, path + (ident,))
            else:
                entry = base_off + target
                payload_rva = u32(data, entry)
                payload_size = u32(data, entry + 4)
                payload_off = rva_to_offset(payload_rva, sections)
                leaves[path + (ident,)] = data[payload_off:payload_off + payload_size]

    walk(0, ())
    return leaves


def verify(exe: Path, version: str, description: str) -> None:
    data = exe.read_bytes()
    resource_rva, resource_size, security_off, security_size, sections = pe_layout(data)
    assert resource_rva and resource_size, 'resource directory missing'
    assert any(name == '.rsrc' for name, *_ in sections), '.rsrc section missing'
    leaves = resource_leaves(data, rva_to_offset(resource_rva, sections), sections)
    types = {path[0] for path in leaves}
    required = {RT_ICON, RT_GROUP_ICON, RT_VERSION, RT_MANIFEST}
    assert required.issubset(types), f'missing resource types: {sorted(required - types)}'

    version_blob = next(blob for path, blob in leaves.items() if path[0] == RT_VERSION)
    version_text = version_blob.decode('utf-16le', errors='ignore')
    for expected in ('KeystoneLens Companion', description, version):
        assert expected in version_text, f'VERSIONINFO missing {expected!r}'

    manifest = next(blob for path, blob in leaves.items() if path[0] == RT_MANIFEST).decode('utf-8')
    assert 'requestedExecutionLevel level="asInvoker"' in manifest
    assert '>true/pm</dpiAware>' in manifest
    assert '>true</longPathAware>' in manifest

    group = next(blob for path, blob in leaves.items() if path[0] == RT_GROUP_ICON)
    assert len(group) >= 6 and u16(group, 2) == 1 and u16(group, 4) >= 1, 'invalid group icon'

    # Signing is an external release gate. Make its state explicit rather than
    # mistaking resources for an Authenticode signature.
    status = 'signed' if security_off and security_size else 'unsigned'
    print(f'{exe}: resources OK; Authenticode={status}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--description', required=True)
    args = parser.parse_args()
    verify(args.exe, args.version, args.description)


if __name__ == '__main__':
    main()
