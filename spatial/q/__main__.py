from .compiler import SQCompileError
from .runtime import SQRuntimeError, main
from . import backends

try:
    main()
except (SyntaxError, SQCompileError, SQRuntimeError, backends.BackendUnavailable) as e:
    raise SystemExit(f"spatialq: {e}")
