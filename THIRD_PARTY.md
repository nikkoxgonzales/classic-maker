# Third-party software

Classic Maker code and its original logo are copyright © 2026 Nikko Gonzales,
licensed under GPL-3.0-or-later. See [LICENSE](LICENSE). There is no warranty.
Your own videos and exported movies are not licensed by this project.

## FFmpeg is a separate program

Classic Maker invokes [FFmpeg](https://ffmpeg.org/) as a subprocess. Portable
Classic Maker archives **do not contain FFmpeg**. Use an existing installation,
or explicitly click **Set up FFmpeg** to download it directly from the publisher's
[imageio-ffmpeg 0.6.0 wheels on PyPI](https://pypi.org/project/imageio-ffmpeg/0.6.0/).
The download is verified against the publisher's SHA-256 digest. The unmodified
executable is installed in your user data directory, not in the app archive.

FFmpeg's license depends on the build: LGPL-2.1-or-later by default; builds with
GPL components such as libx264 use the GPL. The imageio wheels contain GPL-enabled
builds. Run the selected executable with `-version` and `-L` to inspect its build
and license. These licenses are independent of the imageio wrapper's BSD license.

- FFmpeg source and licensing: https://ffmpeg.org/download.html and https://ffmpeg.org/legal.html
- imageio-ffmpeg source, wheel builders, and version mapping: https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0
- Windows build provider: https://www.gyan.dev/ffmpeg/builds/
- Binary distribution and upstream build references: https://github.com/imageio/imageio-binaries/tree/master/ffmpeg
- libx264 source: https://code.videolan.org/videolan/x264

If you redistribute an FFmpeg binary yourself, comply with **that build's**
license, notices, and corresponding-source requirements. This repository does
not provide permission to omit them. An installation from your operating system's
package manager is supported, too.

## Portable launcher runtime

PyInstaller packages an unmodified Python runtime and standard library. Python
uses the [PSF license](https://docs.python.org/3/license.html). PyInstaller uses
[GPL-2.0-or-later with a bootloader exception](https://pyinstaller.org/en/stable/license.html)
allowing bundled applications to retain their own license. Portable archives
include the Python license and PyInstaller bootloader license/exception in
`notices/`, alongside this notice and the project's license.

## HTTPS certificate trust

`classic_maker/cacert.pem` is the unmodified Mozilla CA bundle extracted by curl
on 2026-09-25, verified against its published SHA-256. It is MPL-2.0-licensed;
the full license is in `classic_maker/cacert.LICENSE` and portable `notices/`.
Source and conversion details: https://curl.se/docs/caextract.html
This supplies verified TLS trust on portable Python installations without a
system CA store. It supplements system trust; certificate checks are never disabled.


Windows Movie Maker is a Microsoft product. Classic Maker is an independent
project inspired by its simplicity, not affiliated with or endorsed by Microsoft.
