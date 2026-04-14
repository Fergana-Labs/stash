"""
Yjs document manager: in-memory doc management, WebSocket relay, debounced persistence.

Speaks the y-websocket binary protocol:
  - messageSync = 0 (sync step 1, sync step 2, sync update)
  - messageAwareness = 1
"""
import asyncio
import logging
from uuid import UUID

from fastapi import WebSocket
from pycrdt import Doc

from ..services import notebook_service
from ..services.yjs_converter import (
    apply_markdown_update,
    build_fragment_from_markdown,
    cached_yjs_to_markdown,
    markdown_to_yjs_state,
)

logger = logging.getLogger("octopus.yjs")

MSG_SYNC = 0
MSG_AWARENESS = 1

SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2

DEBOUNCE_SECONDS = 2.0
UNLOAD_GRACE_SECONDS = 60.0


def _encode_varint(n: int) -> bytes:
    """Encode an unsigned integer as a variable-length integer."""
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode a varint from data at offset. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while offset < len(data):
        b = data[offset]
        result |= (b & 0x7F) << shift
        offset += 1
        if (b & 0x80) == 0:
            break
        shift += 7
    return result, offset


class YjsDocHandle:
    """Manages a single Yjs document in memory."""

    def __init__(self, file_id: UUID, workspace_id: UUID | str | None):
        self.file_id = file_id
        self.workspace_id = workspace_id
        self.doc = Doc()
        self.clients: set[WebSocket] = set()
        self.awareness_states: dict[int, bytes] = {}
        self._save_task: asyncio.Task | None = None
        self._unload_task: asyncio.Task | None = None
        self._dirty = False
        self._loaded = False

    async def load_from_db(self):
        """Load Yjs state from database, falling back to content_markdown."""
        if self._loaded:
            return
        state = await notebook_service.get_yjs_state(self.file_id)
        if state:
            try:
                self.doc.apply_update(state)
                # Validate: if the old state used Y.Text instead of Y.XmlFragment
                # under "default", it's incompatible with TipTap. Discard it.
                from pycrdt import XmlFragment
                keys = list(self.doc.keys()) if hasattr(self.doc, 'keys') else []
                if "default" in keys and not isinstance(self.doc["default"], XmlFragment):
                    logger.warning(f"Incompatible Yjs type for file {self.file_id}, resetting")
                    self.doc = Doc()
                    state = None
            except Exception:
                logger.warning(f"Failed to apply stored Yjs state for file {self.file_id}, starting fresh")
                self.doc = Doc()
                state = None

        if not state:
            # No Yjs state — try to bootstrap from content_markdown
            markdown = await notebook_service.get_page_markdown(self.file_id)
            if markdown:
                build_fragment_from_markdown(self.doc, markdown)
                # Persist the generated Yjs state so future loads skip this path
                yjs_state = self.doc.get_update()
                await notebook_service.save_yjs_state(self.file_id, yjs_state, content_markdown=markdown)
                logger.info(f"Bootstrapped Yjs state from markdown for file {self.file_id}")

        self._loaded = True

    def get_state_vector(self) -> bytes:
        return self.doc.get_state()

    def get_update(self, state_vector: bytes | None = None) -> bytes:
        if state_vector:
            return self.doc.get_update(state_vector)
        return self.doc.get_update()

    def apply_update(self, update: bytes):
        self.doc.apply_update(update)
        self._dirty = True

    async def save_to_db(self):
        """Persist current Yjs binary state and extracted markdown to database."""
        if not self._dirty:
            return
        state = self.doc.get_update()
        markdown = cached_yjs_to_markdown(str(self.file_id), state)
        await notebook_service.save_yjs_state(
            self.file_id, state, content_markdown=markdown
        )
        self._dirty = False
        logger.debug(f"Saved Yjs state for file {self.file_id}")

    def schedule_save(self):
        """Schedule a debounced save."""
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        self._save_task = asyncio.create_task(self._debounced_save())

    async def _debounced_save(self):
        try:
            await asyncio.sleep(DEBOUNCE_SECONDS)
            await self.save_to_db()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(f"Error saving Yjs state for file {self.file_id}")

    def add_client(self, ws: WebSocket):
        if self._unload_task and not self._unload_task.done():
            self._unload_task.cancel()
            self._unload_task = None
        self.clients.add(ws)

    def remove_client(self, ws: WebSocket):
        self.clients.discard(ws)

    @property
    def has_clients(self) -> bool:
        return len(self.clients) > 0


class YjsManager:
    """Global Yjs document manager."""

    def __init__(self):
        self._docs: dict[UUID, YjsDocHandle] = {}

    async def get_or_create_handle(self, file_id: UUID, workspace_id: UUID | str | None) -> YjsDocHandle:
        if file_id not in self._docs:
            handle = YjsDocHandle(file_id, workspace_id)
            await handle.load_from_db()
            self._docs[file_id] = handle
        return self._docs[file_id]

    def get_handle(self, file_id: UUID) -> YjsDocHandle | None:
        return self._docs.get(file_id)

    async def handle_ws_connect(self, ws: WebSocket, file_id: UUID, workspace_id: UUID | str | None):
        """Handle a new WebSocket client connecting for Yjs sync."""
        handle = await self.get_or_create_handle(file_id, workspace_id)
        handle.add_client(ws)

        # Send sync step 1 to client (ask for their state vector)
        sv = handle.get_state_vector()
        msg = bytes([MSG_SYNC, SYNC_STEP1]) + _encode_varint(len(sv)) + sv
        await ws.send_bytes(msg)

        # Send current awareness states
        for awareness_data in handle.awareness_states.values():
            await ws.send_bytes(bytes([MSG_AWARENESS]) + awareness_data)

    async def handle_ws_message(self, ws: WebSocket, file_id: UUID, data: bytes):
        """Handle an incoming binary Yjs message from a WebSocket client."""
        handle = self._docs.get(file_id)
        if not handle or len(data) < 2:
            return

        msg_type = data[0]

        if msg_type == MSG_SYNC:
            sync_type = data[1]

            if sync_type == SYNC_STEP1:
                # Client sent their state vector — send them missing updates
                sv_len, offset = _decode_varint(data, 2)
                state_vector = data[offset:offset + sv_len]
                update = handle.get_update(state_vector)
                msg = bytes([MSG_SYNC, SYNC_STEP2]) + _encode_varint(len(update)) + update
                await ws.send_bytes(msg)

            elif sync_type == SYNC_STEP2:
                # Client sent missing updates to us
                update_len, offset = _decode_varint(data, 2)
                update = data[offset:offset + update_len]
                handle.apply_update(update)
                handle.schedule_save()

            elif sync_type == SYNC_UPDATE:
                # Client sent an update
                update_len, offset = _decode_varint(data, 2)
                update = data[offset:offset + update_len]
                handle.apply_update(update)
                handle.schedule_save()
                # Relay to other clients
                for client in handle.clients:
                    if client is not ws:
                        try:
                            await client.send_bytes(data)
                        except Exception:
                            pass

        elif msg_type == MSG_AWARENESS:
            # Relay awareness to all other clients
            awareness_data = data[1:]
            # Store awareness state (keyed by first few bytes which contain client id)
            # Just relay it
            for client in handle.clients:
                if client is not ws:
                    try:
                        await client.send_bytes(data)
                    except Exception:
                        pass

    async def handle_ws_disconnect(self, ws: WebSocket, file_id: UUID):
        """Handle a WebSocket client disconnecting."""
        handle = self._docs.get(file_id)
        if not handle:
            return

        handle.remove_client(ws)

        # Save immediately if dirty
        await handle.save_to_db()

        # Schedule unload if no more clients
        if not handle.has_clients:
            handle._unload_task = asyncio.create_task(
                self._delayed_unload(file_id)
            )

    async def _delayed_unload(self, file_id: UUID):
        """Unload doc from memory after grace period."""
        try:
            await asyncio.sleep(UNLOAD_GRACE_SECONDS)
            handle = self._docs.get(file_id)
            if handle and not handle.has_clients:
                await handle.save_to_db()
                del self._docs[file_id]
                logger.debug(f"Unloaded Yjs doc for file {file_id}")
        except asyncio.CancelledError:
            pass

    async def apply_rest_update(self, file_id: UUID, workspace_id: UUID | str | None, content: str) -> None:
        """Convert markdown to Yjs state and update the in-memory doc + broadcast to connected editors."""
        handle = self._docs.get(file_id)
        if handle:
            # Apply update to live doc and get incremental diff
            update = apply_markdown_update(handle.doc, content)
            handle._dirty = True

            # Broadcast the update to connected editors
            update_msg = bytes([MSG_SYNC, SYNC_UPDATE]) + _encode_varint(len(update)) + update
            for client in handle.clients:
                try:
                    await client.send_bytes(update_msg)
                except Exception:
                    pass
            await handle.save_to_db()
        else:
            # No editors connected — create Yjs state and save directly
            yjs_state = markdown_to_yjs_state(content)
            await notebook_service.save_yjs_state(file_id, yjs_state, content_markdown=content)


yjs_manager = YjsManager()
