from __future__ import annotations

from pathlib import Path
import shutil
from setuptools import Distribution, Extension
from setuptools.command.build_ext import build_ext

compile_args = ["-march=native", "-O3", "-msse", "-msse2", "-mfma", "-mfpmath=sse"]
link_args: list[str] = []
include_dirs: list[str] = []
libraries: list[str] = ["m"]


def build():
    try:
        from Cython.Build import cythonize
    except ImportError:
        raise SystemError("Install Cython first")

    extensions = [
        Extension(
            "*",
            ["fm/*.pyx"],
            extra_compile_args=compile_args,
            extra_link_args=link_args,
            include_dirs=include_dirs,
            libraries=libraries,
        )
    ]
    ext_modules = cythonize(
        extensions,
        include_path=include_dirs,
        language_level=3,
        compiler_directives={"binding": True, "linetrace": True},
    )

    distribution = Distribution({"name": "fm", "ext_modules": ext_modules})
    distribution.package_dir = {"fm": "fm"}

    cmd = build_ext(distribution)
    cmd.ensure_finalized()
    cmd.run()

    # Copy built extensions back to the project
    for output in cmd.get_outputs():
        relative_extension = Path(output).relative_to(cmd.build_lib)
        shutil.copyfile(output, relative_extension)
        mode = relative_extension.stat().st_mode
        mode |= (mode & 0o444) >> 2
        relative_extension.chmod(mode)


if __name__ == "__main__":
    build()
