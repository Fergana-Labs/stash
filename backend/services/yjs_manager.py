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

from pycrdt import Doc, Text

from ..services import workspace_service

logger = logging.getLogger("moltchat.yjs")

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

    def __init__(self, file_id: UUID, workspace_id: UUID):
        self.file_id = file_id
        self.workspace_id = workspace_id
        self.doc = Doc()
        self.text: Text = self.doc.get("default", type=Text)
        self.clients: set[WebSocket] = set()
        self.awareness_states: dict[int, bytes] = {}
        self._save_task: asyncio.Task | None = None
        self._unload_task: asyncio.Task | None = None
        self._dirty = False
        self._loaded = False

    async def load_from_db(self):
        """Load Yjs state from database."""
        if self._loaded:
            return
        state = await workspace_service.get_yjs_state(self.file_id, self.workspace_id)
        if state:
            try:
                self.doc.apply_update(state)
            except Exception:
                logger.warning(f"Failed to apply stored Yjs state for file {self.file_id}")
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

    def get_content_markdown(self) -> str:
        return str(self.text)

    def set_full_content(self, content: str) -> bytes:
        """Replace all text content. Returns the Yjs update bytes (diff from before)."""
        sv_before = self.doc.get_state()
        with self.doc.transaction():
            current = str(self.text)
            if current:
                del self.text[0:len(current)]
            if content:
                self.text.insert(0, content)
        self._dirty = True
        # Return only the diff update
        return self.doc.get_update(sv_before)

    async def save_to_db(self):
        """Persist current state to database."""
        if not self._dirty:
            return
        state = self.doc.get_update()
        content = self.get_content_markdown()
        await workspace_service.save_yjs_state(
            self.file_id, self.workspace_id, state, content
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

    async def get_or_create_handle(self, file_id: UUID, workspace_id: UUID) -> YjsDocHandle:
        if file_id not in self._docs:
            handle = YjsDocHandle(file_id, workspace_id)
            await handle.load_from_db()
            self._docs[file_id] = handle
        return self._docs[file_id]

    def get_handle(self, file_id: UUID) -> YjsDocHandle | None:
        return self._docs.get(file_id)

    async def handle_ws_connect(self, ws: WebSocket, file_id: UUID, workspace_id: UUID):
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

    async def apply_rest_update(self, file_id: UUID, workspace_id: UUID, content: str) -> bytes | None:
        """Apply a REST content update through Yjs and broadcast to connected clients.
        Returns the update bytes, or None if no handle exists."""
        handle = await self.get_or_create_handle(file_id, workspace_id)

        # Apply the full text replacement
        update = handle.set_full_content(content)

        # Save to DB
        state = handle.doc.get_update()
        await workspace_service.save_yjs_state(
            file_id, workspace_id, state, content
        )
        handle._dirty = False

        # Broadcast the update to connected WebSocket clients
        if handle.has_clients:
            msg = bytes([MSG_SYNC, SYNC_UPDATE]) + _encode_varint(len(update)) + update
            for client in handle.clients:
                try:
                    await client.send_bytes(msg)
                except Exception:
                    pass

        # Clean up if no clients
        if not handle.has_clients:
            handle._unload_task = asyncio.create_task(
                self._delayed_unload(file_id)
            )

        return update


yjs_manager = YjsManager()
