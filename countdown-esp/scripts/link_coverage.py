# PlatformIO extra script for the native env: build_flags only reach the compiler, so the
# test binary also needs --coverage at link time to write the .gcda files gcovr reads.
Import("env")  # noqa: F821  (SCons injects Import)

env.Append(LINKFLAGS=["--coverage"])  # noqa: F821
