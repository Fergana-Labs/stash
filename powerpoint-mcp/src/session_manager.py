"""
Session Manager for PowerPoint MCP Server
Handles presentation sessions with in-memory Aspose.Slides presentations
"""

import asyncio
import io
import os
import gc
import uuid
import base64
import tempfile
import logging
import threading
import zipfile

from src.utils import strip_aspose_metadata
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

import aspose.slides as slides

logger = logging.getLogger(__name__)


def dispose_presentation(presentation) -> None:
    """Release an Aspose Presentation's underlying .NET memory.

    Aspose.Slides for Python via .NET doesn't expose dispose() — the
    only way to release .NET-side memory is through the context manager
    protocol (__exit__).  Python's del/gc.collect cannot free it.
    """
    _dispose_aspose(presentation)


def dispose_image(image) -> None:
    """Release an Aspose IImage's underlying .NET memory.

    IImage objects from slide.get_image() hold native bitmap memory
    on the .NET side. Must be disposed via __exit__ like Presentations.
    """
    _dispose_aspose(image)


def _dispose_aspose(obj) -> None:
    if obj is None:
        return
    obj_type = type(obj).__name__
    exit_fn = getattr(obj, "__exit__", None)
    if callable(exit_fn):
        try:
            exit_fn(None, None, None)
            logger.info("Disposed %s via __exit__", obj_type)
        except Exception as e:
            logger.warning("Error disposing %s: %s", obj_type, e)
    else:
        logger.warning("%s has no __exit__ method — cannot dispose .NET memory", obj_type)


@dataclass
class PowerPointSession:
    """Represents an active PowerPoint editing session"""
    session_id: str
    presentation: slides.Presentation
    file_name: str
    temp_dir: str
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    style_palette: Optional[List[Dict[str, Any]]] = None  # Cached style palette from style extraction
    style_guide: Optional[Dict[str, Any]] = None  # Cached full style guide (palette + shape styles)
    initial_slide_xml_cache: Optional[Dict[int, bytes]] = None  # Immutable "before" state from open
    slide_xml_cache: Optional[Dict[int, bytes]] = None           # Updated after each save
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)     # Prevents concurrent Aspose ops on same presentation


class SessionManager:
    """
    Manages PowerPoint presentation sessions.

    Each session:
    - Has a unique session_id
    - Holds an Aspose Presentation object in memory
    - Has a temp directory for intermediate file operations

    Memory management:
    - Max MAX_SESSIONS concurrent sessions (LRU eviction on overflow)
    - Sessions idle > SESSION_TTL_MINUTES are cleaned up
    - Cleanup runs every CLEANUP_INTERVAL_SECONDS
    """

    MAX_SESSIONS = 3
    SESSION_TTL_MINUTES = 30
    CLEANUP_INTERVAL_SECONDS = 60

    _instance: Optional["SessionManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.sessions: Dict[str, PowerPointSession] = {}

        self.MAX_SESSIONS = self._get_int_env("MAX_SESSIONS", self.MAX_SESSIONS)
        self.SESSION_TTL_MINUTES = self._get_int_env("SESSION_TIMEOUT_MINUTES", self.SESSION_TTL_MINUTES)
        self.CLEANUP_INTERVAL_SECONDS = self._get_int_env("SESSION_CLEANUP_INTERVAL_SECONDS", self.CLEANUP_INTERVAL_SECONDS)

        self._setup_license()
        self._start_cleanup_thread()
        logger.info("SessionManager initialized (max_sessions=%d, ttl=%dm, cleanup_interval=%ds)",
                     self.MAX_SESSIONS, self.SESSION_TTL_MINUTES, self.CLEANUP_INTERVAL_SECONDS)

    @staticmethod
    def _get_int_env(name: str, default: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default

        try:
            parsed = int(value)
            if parsed <= 0:
                raise ValueError("must be positive")
            return parsed
        except Exception:
            logger.warning("Invalid %s=%r, using default=%d", name, value, default)
            return default

    def _start_cleanup_thread(self):
        """Start a daemon thread that periodically cleans up stale sessions."""
        thread = threading.Thread(target=self._cleanup_stale_sessions, daemon=True)
        thread.start()
        logger.info("Session cleanup thread started (interval=%ds, TTL=%dm)",
                     self.CLEANUP_INTERVAL_SECONDS, self.SESSION_TTL_MINUTES)

    def _cleanup_stale_sessions(self):
        """Sweep stale sessions periodically, closing any that exceed the TTL."""
        ttl = timedelta(minutes=self.SESSION_TTL_MINUTES)

        while True:
            threading.Event().wait(self.CLEANUP_INTERVAL_SECONDS)
            try:
                now = datetime.now()
                stale_ids = [
                    sid for sid, session in self.sessions.items()
                    if (now - session.last_accessed) > ttl
                ]
                for sid in stale_ids:
                    logger.info("Cleaning up stale session %s (idle > %d min)", sid, self.SESSION_TTL_MINUTES)
                    self.close_session(sid)
                if stale_ids:
                    logger.info("Cleanup complete: evicted %d sessions, %d remaining", len(stale_ids), len(self.sessions))
            except Exception as e:
                logger.warning(f"Error during stale session cleanup: {e}")

    def _evict_lru_sessions(self, keep: int):
        """Evict least-recently-used sessions until at most `keep` remain."""
        while len(self.sessions) > keep:
            oldest_sid = min(self.sessions, key=lambda sid: self.sessions[sid].last_accessed)
            logger.info("Evicting LRU session %s (%s) to make room (have %d, max %d)",
                         oldest_sid, self.sessions[oldest_sid].file_name,
                         len(self.sessions), self.MAX_SESSIONS)
            self.close_session(oldest_sid)

    @staticmethod
    def _extract_slide_xml_from_bytes(pptx_bytes: bytes) -> Dict[int, bytes]:
        """Extract per-slide XML bytes from PPTX bytes (treated as a ZIP).

        Returns dict mapping 1-based slide number to raw XML bytes.
        """
        xml_map = {}
        try:
            with zipfile.ZipFile(io.BytesIO(pptx_bytes), 'r') as z:
                for name in z.namelist():
                    if name.startswith('ppt/slides/slide') and name.endswith('.xml'):
                        try:
                            num = int(name[len('ppt/slides/slide'):-len('.xml')])
                            xml_map[num] = z.read(name)
                        except ValueError:
                            continue
        except Exception as e:
            logger.warning(f"Failed to extract slide XML cache: {e}")
        return xml_map

    def _setup_license(self):
        """Set up Aspose.Slides license from environment variable"""
        license_data = os.environ.get("ASPOSE_LICENSE_DATA")
        if license_data:
            try:
                # Decode base64 license data and apply
                license_bytes = base64.b64decode(license_data)
                license_path = tempfile.mktemp(suffix=".lic")
                with open(license_path, "wb") as f:
                    f.write(license_bytes)

                lic = slides.License()
                lic.set_license(license_path)
                os.remove(license_path)
                logger.info("Aspose.Slides license activated")
            except Exception as e:
                logger.warning(f"Failed to activate Aspose license: {e}. Running in trial mode.")
        else:
            logger.info("No Aspose license found. Running in trial mode (30-day limit).")

    def create_session(self, file_data: str, file_name: str, skip_xml_cache: bool = False) -> PowerPointSession:
        """
        Create a new session from base64-encoded file data.

        Args:
            file_data: Base64-encoded .pptx file content
            file_name: Original filename for reference
            skip_xml_cache: Skip capturing the initial slide XML cache

        Returns:
            PowerPointSession with the loaded presentation
        """
        # Evict oldest sessions if at capacity
        self._evict_lru_sessions(self.MAX_SESSIONS - 1)

        session_id = str(uuid.uuid4())

        # Create temp directory for this session
        temp_dir = tempfile.mkdtemp(prefix=f"pptx_session_{session_id[:8]}_")

        # Decode and save the file
        file_bytes = base64.b64decode(file_data)
        temp_file_path = os.path.join(temp_dir, file_name)
        with open(temp_file_path, "wb") as f:
            f.write(file_bytes)

        # Load the presentation
        presentation = slides.Presentation(temp_file_path)

        xml_cache = None
        if not skip_xml_cache:
            # Cache Aspose-serialized slide XML for consistent comparison with saves.
            # Uses Aspose serialization so both "before" and "after" XML go through the same
            # serializer, ensuring byte comparison reliably detects real changes.
            from .tools.creation_tools import _get_slide_xml_map
            xml_cache = _get_slide_xml_map(presentation)

        session = PowerPointSession(
            session_id=session_id,
            presentation=presentation,
            file_name=file_name,
            temp_dir=temp_dir,
            initial_slide_xml_cache=xml_cache,
            slide_xml_cache=xml_cache,
        )

        self.sessions[session_id] = session
        logger.info(f"Created session {session_id} for {file_name}")

        return session

    def create_empty_session(self, file_name: str = "presentation.pptx") -> PowerPointSession:
        """
        Create a new session with an empty presentation.

        Args:
            file_name: Name for the new presentation

        Returns:
            PowerPointSession with a new empty presentation
        """
        # Evict oldest sessions if at capacity
        self._evict_lru_sessions(self.MAX_SESSIONS - 1)

        session_id = str(uuid.uuid4())

        # Create temp directory for this session
        temp_dir = tempfile.mkdtemp(prefix=f"pptx_session_{session_id[:8]}_")

        # Create new empty presentation
        presentation = slides.Presentation()

        session = PowerPointSession(
            session_id=session_id,
            presentation=presentation,
            file_name=file_name,
            temp_dir=temp_dir,
        )

        self.sessions[session_id] = session
        logger.info(f"Created empty session {session_id}")

        return session

    def get_session(self, session_id: str) -> Optional[PowerPointSession]:
        """
        Get a session by ID.

        Args:
            session_id: The session UUID

        Returns:
            PowerPointSession if found, None otherwise
        """
        session = self.sessions.get(session_id)
        if session:
            session.last_accessed = datetime.now()
        return session

    def save_session(self, session_id: str, close_session: bool = True) -> tuple[str, str]:
        """
        Save the presentation and return base64-encoded file data.

        Args:
            session_id: The session UUID
            close_session: Whether to close the session after saving

        Returns:
            Tuple of (base64_file_data, file_name)
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Save to temp file
        temp_file_path = os.path.join(session.temp_dir, f"saved_{session.file_name}")
        session.presentation.save(temp_file_path, slides.export.SaveFormat.PPTX)
        strip_aspose_metadata(temp_file_path)

        # Read and encode
        with open(temp_file_path, "rb") as f:
            file_bytes = f.read()

        file_data = base64.b64encode(file_bytes).decode("utf-8")
        file_name = session.file_name

        logger.info(f"Saved session {session_id}")
        if close_session:
            self.close_session(session_id)

        return file_data, file_name

    def close_session(self, session_id: str) -> bool:
        """
        Close a session and clean up resources.

        Args:
            session_id: The session UUID

        Returns:
            True if session was closed, False if not found
        """
        import resource as res
        session = self.sessions.pop(session_id, None)
        if not session:
            return False

        mem_before = res.getrusage(res.RUSAGE_SELF).ru_maxrss
        dispose_presentation(session.presentation)

        # Clear XML caches first to free memory before GC
        session.initial_slide_xml_cache = None
        session.slide_xml_cache = None
        session.style_palette = None
        session.style_guide = None
        session.presentation = None

        # Clean up temp directory
        try:
            import shutil
            shutil.rmtree(session.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Error cleaning up temp dir: {e}")

        # Force GC to release Aspose's underlying .NET objects
        gc.collect()

        mem_after = res.getrusage(res.RUSAGE_SELF).ru_maxrss
        logger.info("Closed session %s, %d sessions remaining (RSS: %d KB before -> %d KB after, delta=%+d KB)",
                     session_id, len(self.sessions), mem_before, mem_after, mem_after - mem_before)
        return True

    def get_presentation(self, session_id: str) -> slides.Presentation:
        """
        Get the Aspose Presentation object for a session.

        Args:
            session_id: The session UUID

        Returns:
            Aspose Presentation object

        Raises:
            ValueError if session not found
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        return session.presentation

    def list_sessions(self) -> list[Dict[str, Any]]:
        """
        List all active sessions.

        Returns:
            List of session info dictionaries
        """
        return [
            {
                "session_id": s.session_id,
                "file_name": s.file_name,
                "created_at": s.created_at.isoformat(),
                "last_accessed": s.last_accessed.isoformat(),
                "slide_count": s.presentation.slides.length,
            }
            for s in self.sessions.values()
        ]


# Singleton accessor
def get_session_manager() -> SessionManager:
    """Get the global SessionManager instance"""
    return SessionManager()
