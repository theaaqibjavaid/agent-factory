"""NeuraHive v2 core namespace.

Phase 0 establishes this package boundary. Public runtime contracts are
introduced incrementally during Phase 1+; platform/Studio modules must never
be imported from this namespace.
"""

__version__ = "2.0.0.dev0"

# Keep the export surface explicit even while the v2 contracts are introduced.
__all__: list[str] = ["__version__"]
