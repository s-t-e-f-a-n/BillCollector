"""Opt-in, bounded ZIP transport for one unchanged PDF download."""

import io
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_PDF_BYTES = 64 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024
# One central-directory record fits in 46 + 3 * 65535 bytes. Bound reads
# before ZipFile can allocate a large table of tiny, unwanted members.
_MAX_ZIP_READ_BYTES = 256 * 1024


class _BoundedZipReader(io.BufferedReader):
    def read(self, size=-1):
        if size > _MAX_ZIP_READ_BYTES:
            raise ValueError("ZIP metadata exceeds the read bound")
        data = super().read(_MAX_ZIP_READ_BYTES + 1 if size < 0 else size)
        if len(data) > _MAX_ZIP_READ_BYTES:
            raise ValueError("ZIP metadata exceeds the read bound")
        return data


@dataclass(frozen=True)
class _PDFDownload:
    """The persistence adapters only need URL, filename and save_as."""

    url: str
    suggested_filename: str
    source: Path

    def save_as(self, target):
        shutil.copyfile(self.source, target)


def _member_name(member):
    # orig_filename retains NULs that ZipInfo.filename silently truncates.
    name = member.orig_filename
    parts = name.split("/")
    if (not name or "\\" in name or ":" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts[-1]) > 255):
        raise ValueError("ZIP member path is unsafe")
    kind = stat.S_IFMT(member.external_attr >> 16)
    if (member.is_dir() or member.external_attr & 0x10
            or kind not in {0, stat.S_IFREG}):
        raise ValueError("ZIP member must be a regular file")
    if not parts[-1].lower().endswith(".pdf"):
        raise ValueError("ZIP member must have a PDF extension")
    return parts[-1]


@contextmanager
def pdf_download(download):
    """Yield a download adapter only after complete bounded validation.

    Never extract archive paths. Read the browser's completed local download,
    stream into a private fixed-name file, and check CRC by reading to EOF.
    No persistence callback runs for an invalid archive. Temporary member
    bytes are removed on success, rejection and callback failure.
    """
    source = download.path()
    if source is None:
        raise ValueError("ZIP download has no completed local file")
    with _BoundedZipReader(Path(source).open("rb", buffering=0)) as transport:
        transport.seek(0, 2)
        if not 0 < transport.tell() <= MAX_ARCHIVE_BYTES:
            raise ValueError("ZIP transport exceeds the archive size bound")
        transport.seek(0)
        with zipfile.ZipFile(transport) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise ValueError("ZIP must contain exactly one member")
            member = members[0]
            filename = _member_name(member)
            if member.flag_bits & 1:
                raise ValueError("Encrypted ZIP members are unsupported")
            if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ValueError("ZIP compression must be stored or deflated")
            if (not 0 < member.file_size <= MAX_PDF_BYTES
                    or not 0 < member.compress_size <= MAX_ARCHIVE_BYTES):
                raise ValueError("ZIP member exceeds the size bounds")
            with tempfile.TemporaryDirectory(prefix="billcollector-pdf-") as directory:
                pdf = Path(directory) / "document.pdf"
                with archive.open(member) as stream, pdf.open("xb") as output:
                    header = stream.read(5)
                    if header != b"%PDF-":
                        raise ValueError("ZIP member has no PDF signature")
                    output.write(header)
                    total = len(header)
                    while chunk := stream.read(min(_CHUNK_BYTES, MAX_PDF_BYTES - total + 1)):
                        total += len(chunk)
                        if total > MAX_PDF_BYTES:
                            raise ValueError("PDF stream exceeds the size bound")
                        output.write(chunk)
                    if total != member.file_size:
                        raise ValueError("PDF size differs from ZIP metadata")
                yield _PDFDownload(str(download.url), filename, pdf)
