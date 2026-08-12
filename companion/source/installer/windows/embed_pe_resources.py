#!/usr/bin/env python3
"""Deterministically add Windows icon, version and manifest resources to a PE32+ file.

The Go linker emits no .rsrc section for these tiny bootstrap executables. This
script appends one resource section without altering code or importing a build-
time resource compiler, keeping the release build self-contained and auditable.
"""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass, field
from pathlib import Path

LANG_EN_US = 0x0409
CP_UNICODE = 0x04B0
RT_ICON = 3
RT_GROUP_ICON = 14
RT_VERSION = 16
RT_MANIFEST = 24


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) // boundary * boundary


def wstr(value: str) -> bytes:
    return (value + "\0").encode("utf-16le")


def pad4(data: bytes) -> bytes:
    return data + b"\0" * ((-len(data)) % 4)


def version_block(key: str, value: bytes, value_length: int, value_type: int, children: list[bytes]) -> bytes:
    head = struct.pack("<HHH", 0, value_length, value_type) + wstr(key)
    head = pad4(head)
    body = head + value
    body = pad4(body)
    body += b"".join(children)
    body = struct.pack("<H", len(body)) + body[2:]
    return body


def make_version_info(version: tuple[int, int, int, int], description: str, original_filename: str) -> bytes:
    major, minor, patch, build = version
    fixed = struct.pack(
        "<13I",
        0xFEEF04BD, 0x00010000,
        (major << 16) | minor, (patch << 16) | build,
        (major << 16) | minor, (patch << 16) | build,
        0x3F, 0, 0x00040004, 0x1, 0, 0, 0,
    )

    strings = {
        "CompanyName": "KeystoneLens",
        "FileDescription": description,
        "FileVersion": ".".join(map(str, version)),
        "InternalName": "KeystoneLens",
        "OriginalFilename": original_filename,
        "ProductName": "KeystoneLens Companion",
        "ProductVersion": ".".join(map(str, version)),
    }
    string_children: list[bytes] = []
    for key, text in strings.items():
        value = wstr(text)
        string_children.append(version_block(key, value, len(value) // 2, 1, []))
    string_table = version_block("040904B0", b"", 0, 1, string_children)
    string_file_info = version_block("StringFileInfo", b"", 0, 1, [string_table])

    translation = struct.pack("<HH", LANG_EN_US, CP_UNICODE)
    var = version_block("Translation", translation, len(translation), 0, [])
    var_file_info = version_block("VarFileInfo", b"", 0, 1, [var])
    return version_block("VS_VERSION_INFO", fixed, len(fixed), 0, [string_file_info, var_file_info])


def parse_ico(path: Path) -> tuple[list[bytes], bytes]:
    raw = path.read_bytes()
    if len(raw) < 6:
        raise ValueError("ICO is truncated")
    reserved, kind, count = struct.unpack_from("<HHH", raw, 0)
    if reserved != 0 or kind != 1 or count < 1:
        raise ValueError("Unsupported ICO")
    entries = []
    images = []
    for index in range(count):
        off = 6 + index * 16
        width, height, colors, reserved_b, planes, bitcount, size, image_off = struct.unpack_from("<BBBBHHII", raw, off)
        if image_off + size > len(raw):
            raise ValueError("ICO image outside file")
        images.append(raw[image_off:image_off + size])
        entries.append(struct.pack("<BBBBHHIH", width, height, colors, reserved_b, planes, bitcount, size, index + 1))
    group = struct.pack("<HHH", 0, 1, count) + b"".join(entries)
    return images, group


@dataclass
class Leaf:
    data: bytes
    codepage: int = 0
    data_entry_offset: int = 0
    data_offset: int = 0


@dataclass
class Dir:
    children: dict[int, "Dir | Leaf"] = field(default_factory=dict)
    offset: int = 0

    @property
    def size(self) -> int:
        return 16 + 8 * len(self.children)


def make_resource_section(items: list[tuple[int, int, int, bytes]], base_rva: int) -> bytes:
    root = Dir()
    leaves: list[Leaf] = []
    for type_id, name_id, lang_id, data in items:
        type_dir = root.children.setdefault(type_id, Dir())
        assert isinstance(type_dir, Dir)
        name_dir = type_dir.children.setdefault(name_id, Dir())
        assert isinstance(name_dir, Dir)
        leaf = Leaf(data)
        name_dir.children[lang_id] = leaf
        leaves.append(leaf)

    dirs: list[Dir] = []
    def collect(node: Dir) -> None:
        dirs.append(node)
        for key in sorted(node.children):
            child = node.children[key]
            if isinstance(child, Dir):
                collect(child)
    collect(root)

    cursor = 0
    for node in dirs:
        node.offset = cursor
        cursor += node.size
    for leaf in leaves:
        leaf.data_entry_offset = cursor
        cursor += 16
    cursor = align(cursor, 8)
    for leaf in leaves:
        cursor = align(cursor, 8)
        leaf.data_offset = cursor
        cursor += len(leaf.data)

    out = bytearray(cursor)
    for node in dirs:
        struct.pack_into("<IIHHHH", out, node.offset, 0, 0, 0, 0, 0, len(node.children))
        entry_off = node.offset + 16
        for key in sorted(node.children):
            child = node.children[key]
            if isinstance(child, Dir):
                target = 0x80000000 | child.offset
            else:
                target = child.data_entry_offset
            struct.pack_into("<II", out, entry_off, key, target)
            entry_off += 8
    for leaf in leaves:
        struct.pack_into("<IIII", out, leaf.data_entry_offset, base_rva + leaf.data_offset, len(leaf.data), leaf.codepage, 0)
        out[leaf.data_offset:leaf.data_offset + len(leaf.data)] = leaf.data
    return bytes(out)


def patch_pe(exe: Path, ico: Path, version: tuple[int, int, int, int], description: str, original_filename: str) -> None:
    data = bytearray(exe.read_bytes())
    if data[:2] != b"MZ":
        raise ValueError("Not a PE executable")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe+4] != b"PE\0\0":
        raise ValueError("Invalid PE signature")
    coff = pe + 4
    sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    if struct.unpack_from("<H", data, opt)[0] != 0x20B:
        raise ValueError("Only PE32+ is supported")
    section_alignment = struct.unpack_from("<I", data, opt + 32)[0]
    file_alignment = struct.unpack_from("<I", data, opt + 36)[0]
    size_headers = struct.unpack_from("<I", data, opt + 60)[0]
    resource_rva, resource_size = struct.unpack_from("<II", data, opt + 112 + 2 * 8)
    if resource_rva or resource_size:
        raise ValueError("PE already has resources; refusing ambiguous repatch")

    section_table = opt + opt_size
    last_end = section_table + sections * 40
    if last_end + 40 > size_headers:
        raise ValueError("No room for another PE section header")

    max_end_rva = 0
    for i in range(sections):
        sh = section_table + i * 40
        virtual_size, virtual_address, raw_size = struct.unpack_from("<III", data, sh + 8)
        max_end_rva = max(max_end_rva, virtual_address + max(virtual_size, raw_size))
    new_rva = align(max_end_rva, section_alignment)

    images, group = parse_ico(ico)
    manifest = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">\n  <assemblyIdentity version="{version[0]}.{version[1]}.{version[2]}.{version[3]}" processorArchitecture="amd64" name="KeystoneLens.Companion" type="win32"/>\n  <description>{description}</description>\n  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security></trustInfo>\n  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application><supportedOS Id="{{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}}"/></application></compatibility>\n  <application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings><dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware><longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware></windowsSettings></application>\n</assembly>\n'''.encode("utf-8")
    version_info = make_version_info(version, description, original_filename)
    items: list[tuple[int, int, int, bytes]] = []
    for idx, image in enumerate(images, 1):
        items.append((RT_ICON, idx, LANG_EN_US, image))
    items.extend([
        (RT_GROUP_ICON, 1, LANG_EN_US, group),
        (RT_VERSION, 1, LANG_EN_US, version_info),
        (RT_MANIFEST, 1, LANG_EN_US, manifest),
    ])
    rsrc = make_resource_section(items, new_rva)
    raw_size = align(len(rsrc), file_alignment)
    raw_ptr = align(len(data), file_alignment)
    if len(data) < raw_ptr:
        data.extend(b"\0" * (raw_ptr - len(data)))
    data.extend(rsrc)
    data.extend(b"\0" * (raw_size - len(rsrc)))

    sh = last_end
    name = b".rsrc\0\0\0"
    data[sh:sh+8] = name
    struct.pack_into("<IIIIIIHHI", data, sh + 8,
                     len(rsrc), new_rva, raw_size, raw_ptr,
                     0, 0, 0, 0, 0x40000040)
    struct.pack_into("<H", data, coff + 2, sections + 1)
    size_initialized = struct.unpack_from("<I", data, opt + 8)[0]
    struct.pack_into("<I", data, opt + 8, size_initialized + raw_size)
    struct.pack_into("<I", data, opt + 56, align(new_rva + len(rsrc), section_alignment))
    struct.pack_into("<II", data, opt + 112 + 2 * 8, new_rva, len(rsrc))
    struct.pack_into("<I", data, opt + 64, 0)  # checksum is recalculated by Authenticode tooling later
    exe.write_bytes(data)


def parse_version(text: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in text.split(".")]
    if len(parts) == 3:
        parts.append(0)
    if len(parts) != 4 or any(not 0 <= p <= 65535 for p in parts):
        raise argparse.ArgumentTypeError("version must be A.B.C or A.B.C.D with 16-bit components")
    return tuple(parts)  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--ico", required=True, type=Path)
    parser.add_argument("--version", required=True, type=parse_version)
    parser.add_argument("--description", required=True)
    parser.add_argument("--original-filename", required=True)
    args = parser.parse_args()
    patch_pe(args.exe, args.ico, args.version, args.description, args.original_filename)


if __name__ == "__main__":
    main()
