Name
Vulnerable package
Severity
Description
CVE-2026-42496
perl::5.40.1-6
CRITICAL
Archive::Tar versions before 3.08 for Perl extract symlinks with attacker controlled targets outside the extraction directory. \_make_special_file() passes the tar header's linkname to symlink() without validating it against absolute paths or .. segments. The secure-extract mode check that guards regular file extraction does not cover the symlink target. A subsequent open through the extracted name reads or writes the attacker chosen path.
CVE-2026-8450
libhttp-daemon-perl::6.16-1
CRITICAL
HTTP::Daemon versions before 6.17 for Perl allow OS command injection via send_file(). send_file() opens its string argument with Perl's 2-arg open(). The 2-arg form interprets magic prefixes: '| cmd' and 'cmd |' open a pipe to a subprocess, '> path' and '>> path' open the path for write or append. Untrusted input passed to send_file() can run OS commands at the daemon process UID. The read-pipe form ('cmd |') also leaks subprocess stdout into the HTTP response body. The write-mode forms can create or truncate files at attacker chosen paths.
CVE-2026-28417
vim::9.1.1230-2
HIGH
Vim is an open source, command line text editor. Prior to version 9.2.0073, an OS command injection vulnerability exists in the `netrw` standard plugin bundled with Vim. By inducing a user to open a crafted URL (e.g., using the `scp://` protocol handler), an attacker can execute arbitrary shell commands with the privileges of the Vim process. Version 9.2.0073 fixes the issue.
CVE-2026-35177
vim::9.1.1230-2
HIGH
Vim is an open source, command line text editor. Prior to 9.2.0280, a path traversal bypass in Vim's zip.vim plugin allows overwriting of arbitrary files when opening specially crafted zip archives, circumventing the previous fix for CVE-2025-53906. This vulnerability is fixed in 9.2.0280.
CVE-2026-9538
perl::5.40.1-6
HIGH
Archive::Tar versions before 3.10 for Perl allow memory exhaustion via attacker controlled entry size field in tar header. \_read_tar() reads each entry's payload with $handle->read($$data, $block), where $block is derived from the entry's 12-byte size field in the tar header with no upper bound on that value. A crafted header declaring a multi-gigabyte size causes Perl to allocate a scalar of that size.
CVE-2026-48962
perl::5.40.1-6
HIGH
IO::Compress versions before 2.220 for Perl can execute arbitrary code in File::GlobMapper via an attacker-controlled output glob. _parseOutputGlob() wraps the caller-supplied output glob string in double quotes and stores it in the parser state; _getFiles() then runs the stored expression through eval STRING. A literal double quote in the output glob closes the dquote wrapper, and the characters that follow are evaluated as Perl. Arbitrary Perl in the output glob executes at the calling process's privilege.
CVE-2026-45186
expat::2.7.1-2
HIGH
In libexpat before 2.8.1, the computational complexity of attribute name collision checks allows a denial of service via moderately sized crafted XML input.
CVE-2026-34982
vim::9.1.1230-2
HIGH
Vim is an open source, command line text editor. Prior to version 9.2.0276, a modeline sandbox bypass in Vim allows arbitrary OS command execution when a user opens a crafted file. The `complete`, `guitabtooltip` and `printheader` options are missing the `P_MLE` flag, allowing a modeline to be executed. Additionally, the `mapset()` function lacks a `check_secure()` call, allowing it to be abused from sandboxed expressions. Commit 9.2.0276 fixes the issue.
CVE-2026-48959
perl::5.40.1-6
HIGH
IO::Uncompress::Unzip versions before 2.220 for Perl allow CPU exhaustion via per-byte read loop in fastForward. fastForward() compares length $offset (the digit count of the offset, 1 to 19) against the chunk size $c instead of $offset itself, so $c shrinks from 16 KiB to 1-19 bytes per iteration. Extracting a named entry from an attacker supplied zip via IO::Uncompress::Unzip->new($zip, Name => $target) drives a per-byte read loop scaling with the entry's compressed size, up to the non-Zip64 4 GiB cap.
CVE-2026-33412
vim::9.1.1230-2
HIGH
Vim is an open source, command line text editor. Prior to version 9.2.0202, a command injection vulnerability exists in Vim's glob() function on Unix-like systems. By including a newline character (\n) in a pattern passed to glob(), an attacker may be able to execute arbitrary shell commands. This vulnerability depends on the user's 'shell' setting. This issue has been patched in version 9.2.0202.

CVE-2026-3805
curl::8.14.1-2+deb13u3
HIGH
When doing a second SMB request to the same host again, curl would wrongly use a data pointer pointing into already freed memory.
CVE-2026-28421
vim::9.1.1230-2
HIGH
Vim is an open source, command line text editor. Versions prior to 9.2.0077 have a heap-buffer-overflow and a segmentation fault (SEGV) exist in Vim's swap file recovery logic. Both are caused by unvalidated fields read from crafted pointer blocks within a swap file. Version 9.2.0077 fixes the issue.
CVE-2026-39881
vim::9.1.1230-2
HIGH
Vim is an open source, command line text editor. Prior to 9.2.0316, a command injection vulnerability in Vim's netbeans interface allows a malicious netbeans server to execute arbitrary Ex commands when Vim connects to it, via unsanitized strings in the defineAnnoType and specialKeys protocol messages. This vulnerability is fixed in 9.2.0316.
CVE-2026-6732
libxml2::2.12.7+dfsg+really2.9.14-2.1+deb13u2
HIGH
A flaw was found in libxml2. This vulnerability occurs when the library processes a specially crafted XML Schema Definition (XSD) validated document that includes an internal entity reference. An attacker could exploit this by providing a malicious document, leading to a type confusion error that causes the application to crash. This results in a denial of service (DoS), making the affected system or application unavailable.
CVE-2026-48961
perl::5.40.1-6
HIGH
IO::Compress versions from 2.207 before 2.220 for Perl ship a zipdetails CLI tool that crashes with undefined subroutine on Info-ZIP Unix Extra Field with 8-byte UID or GID. When decode_ux() in bin/zipdetails handles an Info-ZIP Unix Extra Field (tag 0x7875) with UID Size or GID Size set to 8, causing zipdetails to decode an 8-byte UID or GID value, it dispatches through decodeLitteEndian(), which calls a misnamed helper unpackValueQ. The actual function defined in the same file is unpackValue_Q (with underscore); the call raises 'Undefined subroutine &main::unpackValueQ' and the script exits with status 255. Library callers of IO::Compress and IO::Uncompress are not affected; the defect is in the bundled CLI tool.
CVE-2026-42497
perl::5.40.1-6
HIGH
Archive::Tar versions before 3.08 for Perl extract hardlinks to attacker controlled paths outside the extraction directory. \_make_special_file() passes the tar header's linkname to link() without validating it against absolute paths or .. segments, creating a hardlink that shares the victim file's inode. A subsequent write through the extracted name modifies the victim file, and the post-extraction chmod, chown, and utime block in \_extract_file() (guarded only against symlinks via -l) applies the tar header's mode, owner, and timestamps to the shared inode during extraction alone.
CVE-2026-6276
curl::8.14.1-2+deb13u3
HIGH
Using libcurl, when a custom `Host:` header is first set for an HTTP request and a second request is subsequently done using the same _easy handle_ but without the custom `Host:` header set, the second request would use stale information and pass on cookies meant for the first host in the second request. Leak them.
