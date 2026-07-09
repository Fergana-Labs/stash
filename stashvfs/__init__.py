"""Read-only virtual filesystem over Stash — the model, the shell, and the client
contract that backs them. Shared by the `stash vfs` CLI command and the
`/api/v1/me/vfs` endpoint."""

from .client import MachineVfsClient, VfsClient, VfsClientError
from .model import MountError, StashVfsModel
from .shell import SkillAppVfsShell, VfsCommandResult

__all__ = [
    "MachineVfsClient",
    "MountError",
    "SkillAppVfsShell",
    "StashVfsModel",
    "VfsClient",
    "VfsClientError",
    "VfsCommandResult",
]
