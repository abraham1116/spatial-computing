from .codegen import SQCodegenError
from .compiler import SQCompileError
from .runtime import SQRuntimeError, main
from . import backends

try:
    main()
except (SyntaxError, SQCodegenError, SQCompileError, SQRuntimeError, backends.BackendUnavailable) as e:
    raise SystemExit(f"spatialq: {e}")
